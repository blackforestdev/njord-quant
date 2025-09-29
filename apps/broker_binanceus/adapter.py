from __future__ import annotations

import asyncio
import contextlib
import importlib
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Literal, cast

import structlog

from apps.broker_binanceus.backoff import RestRetry, RestRetryConfig
from core.broker import (
    BalanceSnapshot,
    BrokerOrderAck,
    BrokerOrderReq,
    BrokerOrderUpdate,
    IBroker,
)

BrokerStatus = Literal["NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"]


class DuplicateClientOrderIdError(RuntimeError):
    """Raised when an order with the same client order id already exists."""


def _safe_status(value: Any) -> BrokerStatus:
    status_raw = str(value or "NEW").upper()
    if status_raw not in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "REJECTED"}:
        status_raw = "NEW"
    return cast(BrokerStatus, status_raw)


class BinanceUSBroker(IBroker):
    def __init__(
        self,
        api_key: str | None,
        api_secret: str | None,
        *,
        read_only: bool = True,
        testnet: bool = False,
    ) -> None:
        params: dict[str, Any] = {
            "enableRateLimit": True,
            "timeout": 15000,
            "options": {"adjustForTimeDifference": True},
        }
        if testnet:
            params.setdefault("options", {})["defaultType"] = "spot"
        self._pro_exchange = None
        try:
            ccxt = importlib.import_module("ccxt")
        except ModuleNotFoundError as exc:  # pragma: no cover - environment dependent
            msg = "ccxt package is required for BinanceUSBroker"
            raise RuntimeError(msg) from exc

        self._exchange = ccxt.binanceus(params)
        try:
            ccxtpro = importlib.import_module("ccxtpro")
        except ModuleNotFoundError:  # pragma: no cover - optional
            self._pro_exchange = None
        else:
            self._pro_exchange = ccxtpro.binanceus(params)
            if api_key and api_secret:
                self._pro_exchange.apiKey = api_key
                self._pro_exchange.secret = api_secret
        if api_key and api_secret:
            self._exchange.apiKey = api_key
            self._exchange.secret = api_secret
        self._read_only = read_only
        self._listen_key: str | None = None
        self._last_cancel_update: BrokerOrderUpdate | None = None
        self._log = structlog.get_logger("broker.binanceus.adapter")
        self._rest_retry = RestRetry(
            config=RestRetryConfig(),
            sleep_fn=time.sleep,
            logger=structlog.get_logger("broker.binanceus.rest"),
        )

    def place(self, req: BrokerOrderReq) -> BrokerOrderAck:
        if self._read_only:
            msg = "Broker is in read-only mode"
            raise RuntimeError(msg)
        try:
            order = self._with_retries(
                lambda: self._exchange.create_order(
                    symbol=req.symbol,
                    type=req.type,
                    side=req.side,
                    amount=req.qty,
                    price=req.limit_price,
                    params={"clientOrderId": req.client_order_id},
                )
            )
        except Exception as exc:
            if self._is_duplicate_client_order(exc):
                existing = self._fetch_order_by_client_id(req.client_order_id)
                if existing is None:
                    raise DuplicateClientOrderIdError from exc
                return existing
            raise

        return self._order_to_ack(order, req.client_order_id)

    def cancel(self, exchange_order_id: str) -> bool:
        if self._read_only:
            msg = "Broker is in read-only mode"
            raise RuntimeError(msg)
        try:
            self._with_retries(lambda: self._exchange.cancel_order(exchange_order_id))
        except Exception:
            return False
        update = BrokerOrderUpdate(
            exchange_order_id=exchange_order_id,
            status="CANCELED",
            filled_qty=0.0,
            avg_price=None,
            ts_ns=time.time_ns(),
            raw={"event": "cancel"},
        )
        self._last_cancel_update = update
        return True

    def last_cancel_update(self) -> BrokerOrderUpdate | None:
        return self._last_cancel_update

    def fetch_open_orders(self, symbol: str | None = None) -> list[BrokerOrderUpdate]:
        orders = self._with_retries(self._exchange.fetch_open_orders, symbol)
        return self._transform_orders(orders)

    def fetch_balances(self) -> list[BalanceSnapshot]:
        balances = self._with_retries(self._exchange.fetch_balance)
        total = balances.get("total", {}) or {}
        free = balances.get("free", {}) or {}
        used = balances.get("used", {}) or {}
        snapshots: list[BalanceSnapshot] = []
        timestamp = time.time_ns()
        for asset, _total_qty in total.items():
            snapshots.append(
                BalanceSnapshot(
                    asset=str(asset),
                    free=float(free.get(asset, 0.0) or 0.0),
                    locked=float(used.get(asset, 0.0) or 0.0),
                    ts_ns=timestamp,
                )
            )
        return snapshots

    def fetch_trades(self, since: int | None = None) -> list[dict[str, Any]]:
        trades = self._with_retries(self._exchange.fetch_my_trades, since)
        return [dict(trade) for trade in trades]

    def find_order_by_client_id(self, client_order_id: str) -> BrokerOrderAck | None:
        return self._fetch_order_by_client_id(client_order_id)

    async def _create_listen_key(self) -> None:
        if self._listen_key is not None:
            return
        create = getattr(self._exchange, "privatePostUserDataStream", None)
        if create is None:
            return
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(None, create)
        except Exception:  # pragma: no cover - depends on env
            return
        listen_key = None
        if isinstance(response, dict):
            listen_key = response.get("listenKey")
        if isinstance(listen_key, str):
            self._listen_key = listen_key

    async def _keepalive_loop(self, stop: asyncio.Event) -> None:
        keepalive = getattr(self._exchange, "privatePutUserDataStream", None)
        if keepalive is None or self._listen_key is None:
            return
        loop = asyncio.get_running_loop()
        try:
            while not stop.is_set():
                await asyncio.sleep(1500.0)
                try:
                    await loop.run_in_executor(None, keepalive, {"listenKey": self._listen_key})
                except Exception:  # pragma: no cover - env dependent
                    break
        finally:
            self._listen_key = None

    def _transform_orders(self, orders: list[dict[str, Any]]) -> list[BrokerOrderUpdate]:
        updates: list[BrokerOrderUpdate] = []
        for order in orders:
            updates.append(
                BrokerOrderUpdate(
                    exchange_order_id=str(order.get("id")),
                    status=_safe_status(order.get("status")),
                    filled_qty=float(order.get("filled", 0.0) or 0.0),
                    avg_price=order.get("average"),
                    ts_ns=int(order.get("timestamp") or time.time_ns()),
                    raw=order,
                )
            )
        return updates

    @asynccontextmanager
    async def start_user_stream(
        self,
        poll_interval: float = 2.0,
        *,
        reconnect_max_attempts: int | None = None,
        reconnect_sleep: Callable[[float], Awaitable[None]] | None = None,
        reconnect_rand: Callable[[], float] | None = None,
        reconnect_stop_event: asyncio.Event | None = None,
    ) -> AsyncIterator[AsyncIterator[list[BrokerOrderUpdate]]]:
        queue: asyncio.Queue[list[BrokerOrderUpdate] | None] = asyncio.Queue()
        stop_event = reconnect_stop_event or asyncio.Event()
        if reconnect_stop_event is not None:
            stop_event.clear()
        keepalive_task: asyncio.Task[None] | None = None

        log = self._ensure_log()
        sleep = reconnect_sleep or asyncio.sleep
        rand_fn = reconnect_rand or random.random

        async def pro_loop() -> None:
            assert self._pro_exchange is not None
            failures = 0
            last_warn = 0.0
            warn_interval = 30.0
            base_delay = 1.0
            max_delay = 30.0
            while not stop_event.is_set():
                try:
                    orders = await self._pro_exchange.watch_orders()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures += 1
                    if reconnect_max_attempts is not None and failures >= reconnect_max_attempts:
                        log.warning(
                            "user_stream_reconnect_aborted",
                            attempt=failures,
                            error=str(exc),
                        )
                        stop_event.set()
                        break
                    cap = min(max_delay, base_delay * (2 ** max(failures - 1, 0)))
                    delay = max(0.1, float(rand_fn()) * cap)
                    now = time.monotonic()
                    if failures == 1 or now - last_warn >= warn_interval:
                        log.warning(
                            "user_stream_reconnect",
                            attempt=failures,
                            delay=round(delay, 3),
                            error=str(exc),
                        )
                        last_warn = now
                    if stop_event.is_set():
                        break
                    await sleep(delay)
                    continue
                failures = 0
                last_warn = 0.0
                updates = self._transform_orders(orders)
                if updates:
                    await queue.put(updates)
                if stop_event.is_set():
                    break
                await asyncio.sleep(0)

        async def rest_loop() -> None:
            await self._create_listen_key()
            nonlocal keepalive_task
            keepalive_task = asyncio.create_task(self._keepalive_loop(stop_event))
            last_snapshot: dict[str, BrokerOrderUpdate] = {}
            while not stop_event.is_set():
                current_updates = self.fetch_open_orders()
                current_map = {u.exchange_order_id: u for u in current_updates}
                diff: list[BrokerOrderUpdate] = []
                for oid, update in current_map.items():
                    previous = last_snapshot.get(oid)
                    if (
                        previous is None
                        or previous.status != update.status
                        or previous.filled_qty != update.filled_qty
                        or previous.avg_price != update.avg_price
                    ):
                        diff.append(update)
                missing = set(last_snapshot.keys()) - set(current_map.keys())
                for oid in missing:
                    prev = last_snapshot[oid]
                    diff.append(
                        BrokerOrderUpdate(
                            exchange_order_id=oid,
                            status="CANCELED",
                            filled_qty=prev.filled_qty,
                            avg_price=prev.avg_price,
                            ts_ns=time.time_ns(),
                            raw={"reason": "removed"},
                        )
                    )
                if diff:
                    await queue.put(diff)
                last_snapshot = current_map
                await asyncio.sleep(max(0.5, poll_interval))

        if self._pro_exchange is not None:
            worker = asyncio.create_task(pro_loop())
        else:
            worker = asyncio.create_task(rest_loop())

        async def generator() -> AsyncIterator[list[BrokerOrderUpdate]]:
            try:
                while True:
                    item = await queue.get()
                    if item is None:
                        break
                    yield item
            finally:
                pass

        try:
            yield generator()
        finally:
            stop_event.set()
            queue.put_nowait(None)
            worker.cancel()
            try:
                await asyncio.wait_for(worker, timeout=1.0)
            except asyncio.CancelledError:
                pass
            except TimeoutError:
                log.warning("user_stream_worker_shutdown_timeout")
            except Exception:  # pragma: no cover - defensive cleanup
                log.warning("user_stream_worker_shutdown_error", exc_info=True)
            if keepalive_task is not None:
                keepalive_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await keepalive_task

    def _order_to_ack(self, order: dict[str, Any], client_order_id: str) -> BrokerOrderAck:
        exchange_order_id = str(order.get("id", client_order_id))
        ts_ns = int(order.get("timestamp") or time.time_ns())
        return BrokerOrderAck(
            client_order_id=client_order_id,
            exchange_order_id=exchange_order_id,
            ts_ns=ts_ns,
        )

    def _is_duplicate_client_order(self, exc: Exception) -> bool:
        message = str(getattr(exc, "message", None) or exc)
        indicators = {"Duplicate", "clientOrderId", "-2010", "EEXIST"}
        return any(token in message for token in indicators)

    def _fetch_order_by_client_id(self, client_order_id: str) -> BrokerOrderAck | None:
        fetch = getattr(self._exchange, "fetch_order", None)
        if fetch is None:
            return None
        try:
            order = self._with_retries(fetch, None, params={"clientOrderId": client_order_id})
        except Exception:
            return None
        return self._order_to_ack(order, client_order_id)

    def _with_retries(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        retry = getattr(self, "_rest_retry", None)
        if retry is None:
            retry = RestRetry(config=RestRetryConfig(), sleep_fn=time.sleep)
            self._rest_retry = retry
        return retry.call(func, *args, **kwargs)

    def _ensure_log(self) -> Any:
        log = getattr(self, "_log", None)
        if log is None:
            log = structlog.get_logger("broker.binanceus.adapter")
            self._log = log
        return log

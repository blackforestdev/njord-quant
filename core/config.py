from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast, get_args, get_origin, get_type_hints

from portfolio.contracts import PortfolioConfig

if TYPE_CHECKING:

    class BaseModel:  # pragma: no cover - typing helper only
        model_config: ClassVar[dict[str, Any]]

        def __init__(self, **data: Any) -> None: ...

        @classmethod
        def model_validate(cls, data: Any) -> Any: ...

    def Field(*args: Any, **kwargs: Any) -> Any: ...

else:  # pragma: no cover - imported at runtime
    try:
        from pydantic import BaseModel, Field  # type: ignore[import-untyped]
    except ModuleNotFoundError:  # pragma: no cover - minimal fallback for tests
        _MISSING = object()

        class _FieldInfo:
            def __init__(self, *, default: Any = _MISSING, default_factory: Any = _MISSING) -> None:
                if default is not _MISSING and default_factory is not _MISSING:
                    msg = "Field cannot specify both default and default_factory"
                    raise ValueError(msg)
                self.default = default
                self.default_factory = default_factory

            def get_default(self) -> Any:
                if self.default is not _MISSING:
                    return self.default
                if self.default_factory is not _MISSING:
                    return self.default_factory()
                return _MISSING

        def Field(*, default: Any = _MISSING, default_factory: Any = _MISSING) -> _FieldInfo:  # type: ignore[misc]
            return _FieldInfo(default=default, default_factory=default_factory)

        class BaseModel:
            model_config: ClassVar[dict[str, Any]] = {}

            def __init__(self, **data: Any) -> None:
                type_hints = get_type_hints(self.__class__)
                defaults: dict[str, Any] = {}
                for name in type_hints:
                    attr = getattr(self.__class__, name, _MISSING)
                    if isinstance(attr, _FieldInfo):
                        default_value = attr.get_default()
                        if default_value is not _MISSING:
                            defaults[name] = default_value
                    elif attr is not _MISSING:
                        defaults[name] = attr

                allowed = set(type_hints)
                if self.model_config.get("extra") == "forbid":
                    extra = set(data) - allowed
                    if extra:
                        msg = f"Unexpected fields: {sorted(extra)}"
                        raise TypeError(msg)

                for name in allowed:
                    if name in data:
                        raw_value = data[name]
                    elif name in defaults:
                        raw_value = defaults[name]
                    else:
                        msg = f"Missing required field: {name}"
                        raise TypeError(msg)
                    value = self._convert_value(type_hints[name], raw_value)
                    setattr(self, name, value)

            @classmethod
            def model_validate(cls, data: Any) -> Any:
                if not isinstance(data, Mapping):
                    msg = f"Expected mapping to validate {cls.__name__}, got {type(data)!r}"
                    raise TypeError(msg)
                return cls(**data)

            @staticmethod
            def _convert_value(annotation: Any, value: Any) -> Any:
                origin = get_origin(annotation)
                if origin is list:
                    items = value if isinstance(value, list) else list(value)
                    item_type = get_args(annotation)[0] if get_args(annotation) else Any
                    return [BaseModel._convert_value(item_type, item) for item in items]
                if origin is dict:
                    mapping = value if isinstance(value, dict) else dict(value)
                    key_type, val_type = get_args(annotation) or (Any, Any)
                    return {
                        BaseModel._convert_value(key_type, k): BaseModel._convert_value(val_type, v)
                        for k, v in mapping.items()
                    }
                if (
                    isinstance(annotation, type)
                    and issubclass(annotation, BaseModel)
                    and isinstance(value, Mapping)
                ):
                    return annotation.model_validate(value)
                if annotation is Path and not isinstance(value, Path):
                    return Path(value)
                if annotation in (int, float, bool, str) and not isinstance(value, annotation):
                    return annotation(value)
                return value


class AppCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    name: str
    env: str
    timezone: str


class LoggingCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    level: str = "INFO"
    json: bool = False
    journal_dir: Path


class RedisTopicsCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    trades: str
    book: str
    ticker: str
    intents: str
    risk: str
    orders: str
    fills: str


class RedisCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    url: str
    topics: RedisTopicsCfg


class PostgresCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    dsn: str


class ExchangeCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    venue: str
    symbols: list[str]
    ws_keepalive_sec: int


class RiskCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    per_order_usd_cap: float = 250.0
    daily_loss_usd_cap: float = 300.0
    orders_per_min_cap: int = 30
    kill_switch_file: str = "/var/run/njord.trading.halt"
    kill_switch_key: str = "njord:trading:halt"


class PathsCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    journal_dir: Path
    experiments_dir: Path


class BinanceUSSecretsCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    key: str | None = None
    secret: str | None = None


class ApiKeysCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    binanceus: BinanceUSSecretsCfg | None = None


class SecretsCfg(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    api_keys: ApiKeysCfg | None = None


class Config(BaseModel):
    model_config: ClassVar[dict[str, Any]] = {"extra": "forbid"}

    app: AppCfg
    logging: LoggingCfg
    redis: RedisCfg
    postgres: PostgresCfg
    exchange: ExchangeCfg
    risk: RiskCfg
    paths: PathsCfg
    secrets: SecretsCfg = Field(default_factory=SecretsCfg)
    portfolio: PortfolioConfig | None = None


def _read_yaml(path: Path) -> dict[str, Any]:
    """Safe YAML read; returns {} if file missing/empty."""
    import yaml  # lazy import

    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data or {}


def load_config(base_dir: str | Path) -> Config:
    """Load config models from ./config/base.yaml and optional secrets."""

    base_path = Path(base_dir)
    base_yaml = base_path / "config" / "base.yaml"
    data = _read_yaml(base_yaml)
    if not data:
        msg = f"Missing or empty config file: {base_yaml}"
        raise FileNotFoundError(msg)

    secrets_path = base_path / "config" / "secrets.enc.yaml"
    secrets = _read_yaml(secrets_path)
    if secrets:
        merged = data.setdefault("secrets", {})
        merged.update(secrets)

    if "secrets" in data:
        secrets_dict = data["secrets"] or {}
        if isinstance(secrets_dict, dict) and "api_keys" in secrets_dict:
            api_keys_dict = secrets_dict["api_keys"] or {}
            if isinstance(api_keys_dict, dict) and "binanceus" in api_keys_dict:
                api_keys_dict["binanceus"] = BinanceUSSecretsCfg.model_validate(
                    api_keys_dict["binanceus"]
                )
            secrets_dict["api_keys"] = ApiKeysCfg.model_validate(api_keys_dict)
        data["secrets"] = SecretsCfg.model_validate(secrets_dict)

    return cast(Config, Config.model_validate(data))

from typing import Iterable
from core.contracts import OrderIntent, TradeEvent, BookEvent
from core.time import now_ns

class StrategyBase:
    strategy_id = "base"

    def on_event(self, event) -> Iterable[OrderIntent]:
        # Override in derived classes; yield OrderIntent instances
        return []

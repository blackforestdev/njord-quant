# Clock helpers
import time


def now_ns() -> int:
    "High-resolution local timestamp."
    return time.time_ns()

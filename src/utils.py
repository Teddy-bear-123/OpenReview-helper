import signal
from collections.abc import Sequence
from types import FrameType
from typing import Any, Callable, Optional

import numpy as np


class TimeoutExpiredError(Exception):
    pass


def alarm_handler(signum: int, frame: Optional[FrameType]) -> None:
    raise TimeoutExpiredError("Function call timed out.")


def run_with_timeout(
    func: Callable[..., Any],
    args: Optional[tuple[Any, ...]] = None,
    kwargs: Optional[dict[str, Any]] = None,
    timeout_duration: int = 10,
    default_output: Optional[Any] = None,
) -> Any:
    """Run func with given args and kwargs with timeout"""
    if args is None:
        args = ()
    if kwargs is None:
        kwargs = {}

    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout_duration)

    try:
        result = func(*args, **kwargs)
    except TimeoutExpiredError:
        print(f"Timeout occurred at {func.__name__}, skipping...")
        result = default_output

    signal.alarm(0)
    return result


def int_list_to_str(ints: list[int]) -> str:
    output = ", ".join(str(item) for item in ints)
    return output if output else "-"


def mean(values: Sequence[float], prec: int = 2) -> str:
    if not values:
        return "-"
    mean_val = sum(values) / len(values)
    return f"{mean_val:.{prec}f}"


def std(values: Sequence[float], prec: int = 2) -> str:
    if not values:
        return "-"
    std_val = np.std(values)
    return f"{std_val:.{prec}f}"

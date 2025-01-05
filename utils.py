import signal

import numpy as np


class TimeoutExpired(Exception):
    pass


def alarm_handler(signum, frame):
    raise TimeoutExpired


def run_with_timeout(func, args=(), kwargs={}, timeout_duration=10, default_output=[]):
    """Run func with given args and kwargs with timeout"""
    # Set alarm.
    signal.signal(signal.SIGALRM, alarm_handler)
    signal.alarm(timeout_duration)

    try:
        result = func(*args, **kwargs)
    except TimeoutExpired:
        print(f"Timeout occurred at {func.__name__}, skipping...")
        result = default_output

    # Cancel the alarm.
    signal.alarm(0)
    return result


def int_list_to_str(ints: list[int]) -> str:
    return ", ".join([str(item) for item in ints])


def mean(values: list[int | float], prec: int = 2) -> str:
    if not values:
        return "-"

    mean_val = sum(values) / len(values)
    return f"{mean_val:.{prec}f}"


def std(values: list[int | float], prec: int = 2) -> str:
    if not values:
        return "-"

    std_val = np.std(values)
    return f"{std_val:.{prec}f}"

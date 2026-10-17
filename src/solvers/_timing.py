"""Quy uoc do build/solve dung chung cho cac solver."""

from math import isfinite
from time import perf_counter


def start_build(time_limit, seed):
    if time_limit is not None and (isinstance(time_limit, bool)
            or not isinstance(time_limit, (int, float))
            or not isfinite(time_limit) or time_limit <= 0):
        raise ValueError("time_limit phai duong, huu han hoac None")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("seed phai la so nguyen trong 0..2147483647")
    return perf_counter()


def remaining_budget(started, time_limit):
    return None if time_limit is None else max(0.0, time_limit - (perf_counter() - started))


def finish_build(started, solver, **counts):
    return {"solver": solver, "build_seconds": perf_counter() - started,
            "solve_seconds": 0.0, **counts}


def finish_info(info, status):
    info.update(status=status, total_seconds=info["build_seconds"] + info["solve_seconds"])
    return info


def build_timeout(info):
    return None, finish_info(info, "TIMEOUT")

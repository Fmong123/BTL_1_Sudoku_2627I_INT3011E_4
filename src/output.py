"""Ghi so lieu benchmark, khong ghi ma tran de/loi giai."""

import math

CSV_FIELDS = [
    "source", "puzzle_number", "puzzle_id", "dataset_group", "size", "clues", "difficulty",
    "repeat", "method", "solver", "encoding", "seed", "time_limit", "status",
    "build_seconds", "solve_seconds", "total_seconds", "elapsed_seconds", "variables", "clauses",
    "constraints", "verified", "error", "run_id",
]


def result_values(row):
    values = {key: row.get(key, "") for key in CSV_FIELDS}
    for key, value in values.items():
        if isinstance(value, float):
            values[key] = f"{value:.9f}" if math.isfinite(value) else ""
    return {key: "" if value is None else str(value) for key, value in values.items()}


def write_result(writer, row):
    writer.writerow(result_values(row))

"""Chay cac solver lan luot tren cung bo de; ghi CSV va tong hop."""

import csv
import importlib
import math
import random
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from .analysis import append_results
from .cardinality import ENCODINGS
from .input import iter_puzzle_records
from .output import result_values
from .sudoku import check_solution

SOLVER_LABELS = {"cp-sat": "OR-Tools CP-SAT", "cplex-mip": "CPLEX MIP",
                 "gurobi-mip": "Gurobi MIP", "cplex-cp": "CPLEX CP"}
SOLVER_MODULES = {"sat": "sat_solver", "cp-sat": "cp_sat_solver",
                  "cplex-mip": "cplex_mip_solver", "gurobi-mip": "gurobi_mip_solver",
                  "cplex-cp": "cplex_cp_solver"}


def run_trial(grid, method, encoding="", solver_name="glucose3", time_limit=30, seed=42):
    """Goi solver truc tiep; kiem tra nghiem noi bo, khong ghi bang nghiem."""
    if method not in SOLVER_MODULES:
        raise ValueError(f"Phuong phap khong ho tro: {method}")
    started = perf_counter()
    info = {"solver": solver_name if method == "sat" else SOLVER_LABELS[method]}
    try:
        module = importlib.import_module(f"src.solvers.{SOLVER_MODULES[method]}")
        args = {"time_limit": time_limit, "seed": seed}
        if method == "sat":
            args.update(encoding=encoding, solver_name=solver_name)
        solution, result = module.solve(grid, **args)
        info.update(result)
        if info["status"] == "SAT":
            info["verified"] = solution is not None and check_solution(grid, solution)
            if not info["verified"]:
                info.update(status="ERROR", error="Nghiem Sudoku khong hop le")
        elif solution is not None:
            info.update(status="ERROR", verified=False,
                        error="Solver tra nghiem voi trang thai khong phai SAT")
    except (ImportError, FileNotFoundError) as error:
        info.update(status="UNAVAILABLE", error=str(error))
    except Exception as error:
        info.update(status="ERROR", error=f"{type(error).__name__}: {error}")
    finally:
        info["elapsed_seconds"] = perf_counter() - started
    return info


def _validate_config(methods, encodings, repeats, time_limit, seed, puzzle_numbers):
    if not methods or len(set(methods)) != len(methods) or set(methods) - SOLVER_MODULES.keys():
        raise ValueError("METHODS phai chua cac phuong phap hop le, khong trung nhau")
    if "sat" in methods and (not encodings or len(set(encodings)) != len(encodings)
                             or set(encodings) - set(ENCODINGS)):
        raise ValueError("ENCODINGS phai hop le, khong trung nhau")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("REPEATS phai la so nguyen duong")
    if type(seed) is not int or not 0 <= seed <= 2147483647:
        raise ValueError("SEED phai la so nguyen trong 0..2147483647")
    if time_limit is not None and (isinstance(time_limit, bool)
            or not isinstance(time_limit, (int, float))
            or not math.isfinite(time_limit) or time_limit <= 0):
        raise ValueError("TIME_LIMIT phai duong, huu han hoac None")
    if puzzle_numbers is not None and (not puzzle_numbers
            or any(type(n) is not int or n < 1 for n in puzzle_numbers)
            or len(set(puzzle_numbers)) != len(puzzle_numbers)):
        raise ValueError("PUZZLE_NUMBERS phai chua so nguyen duong khong trung, hoac None")


def run_benchmark(input_path, output_path, summary_path, puzzle_numbers=None,
                  methods=("sat", "cp-sat", "cplex-mip", "gurobi-mip", "cplex-cp"),
                  encodings=("pairwise", "seqcounter", "bitwise", "commander", "product"),
                  sat_solver="glucose3", repeats=1, time_limit=30, seed=42, quiet=False,
                  size_summary_dir=None):
    """Mot/nhieu CSV dau vao -> ket qua chung va tong hop theo kich thuoc."""
    started = perf_counter()
    inputs = [input_path] if isinstance(input_path, (str, Path)) else list(input_path)
    inputs = list(map(Path, inputs))
    output_path, summary_path = map(Path, (output_path, summary_path))
    paths = inputs + [output_path, summary_path]
    if not inputs or len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Can CSV dau vao; cac file dau vao/ket qua/tong hop phai khac nhau")
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"Khong tim thay CSV dau vao: {path}")
    if any(path.suffix.lower() != ".csv" for path in paths):
        raise ValueError("File dau vao, ket qua va tong hop phai la CSV")
    methods, encodings = list(methods), list(encodings)
    puzzle_numbers = None if puzzle_numbers is None else list(puzzle_numbers)
    _validate_config(methods, encodings, repeats, time_limit, seed, puzzle_numbers)
    plans = [(method, encoding) for method in methods
             for encoding in (encodings if method == "sat" else [""])]
    if size_summary_dir is not None:
        root = Path(size_summary_dir).resolve()
        if any(path.resolve().name in {"ket_qua.csv", "tong_hop.csv"}
               and path.resolve().parent.parent == root
               and path.resolve().parent.name.split("x")[0].isdigit()
               for path in paths):
            raise ValueError("File dau vao/ket qua trung voi CSV rieng theo kich thuoc")

    def records():
        for path in inputs:
            for record in iter_puzzle_records(path, puzzle_numbers):
                yield path, record

    run_id = uuid4().hex
    try:
        rows = _run_trials(records(), plans, repeats, sat_solver, time_limit, seed, quiet, run_id)
        append_results(rows, output_path, summary_path, size_summary_dir, plans, repeats)
    except KeyboardInterrupt:
        if not quiet:
            print("Da dung bang Ctrl+C; khong luu dot dang chay. Ket qua cu duoc giu nguyen.", flush=True)
        raise
    if not quiet:
        _print_run_summary(output_path, summary_path, started, "complete", run_id)
        print(f"Ket qua: {output_path}")
        print(f"Tong hop: {summary_path}")
        if size_summary_dir is not None:
            print(f"Ket qua va tong hop rieng: {size_summary_dir}/<size>x<size>/")
    return len(rows)


def _print_run_summary(output_path, summary_path, started, run_state, run_id):
    """Report this run only; scope=all avoids counting size/group views twice."""
    with output_path.open(encoding="utf-8-sig", newline="") as stream:
        puzzles = {(row["source"], row["puzzle_number"]) for row in csv.DictReader(stream)
                   if row["run_id"] == run_id}
    with summary_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [row for row in csv.DictReader(stream)
                if row["scope"] == "all" and row["run_id"] == run_id]
    count = sum(int(row["runs"]) for row in rows)
    timed = sum(int(row["timed_runs"]) for row in rows)
    print(f"\nTong ket dot chay ({run_state}): {len(puzzles)} de, {count} luot da luu")
    print(f"{'Phuong phap':<22} {'Luot':>8} {'Co so do':>12} "
          f"{'Build (s)':>12} {'Solve (s)':>12} {'Total (s)':>12}")
    for row in rows:
        label = row["method"] + ("/" + row["encoding"] if row["encoding"] else "")
        coverage = f"{row['timed_runs']}/{row['runs']}"
        values = [f"{float(row[field + '_sum']):.6f}" if row[field + "_sum"] else "N/A"
                  for field in ("build_seconds", "solve_seconds", "total_seconds")]
        print(f"{label:<22} {row['runs']:>8} {coverage:>12} "
              + " ".join(f"{value:>12}" for value in values))
    total = sum(float(row["total_seconds_sum"]) for row in rows if row["total_seconds_sum"])
    total_text = f"{total:.6f}s" if timed else "N/A"
    print(f"Tong build + solve: {total_text} ({timed}/{count} luot co du so do)")
    elapsed = perf_counter() - started
    hours, remainder = divmod(elapsed, 3600)
    minutes, seconds = divmod(remainder, 60)
    print(f"Tong thoi gian ca dot (doc du lieu, giai, ghi CSV, tong hop): "
          f"{elapsed:.3f}s ({int(hours):02d}:{int(minutes):02d}:{seconds:06.3f})", flush=True)


def _run_trials(records, plans, repeats, sat_solver, time_limit, seed, quiet, run_id):
    rows = []
    for input_path, record in records:
        size = record.get("size")
        size = size if type(size) is int and size > 0 else 0
        base = {"source": str(input_path), "puzzle_number": record["puzzle_number"],
                "puzzle_id": record["puzzle_id"], "dataset_group": record["dataset_group"],
                "size": size, "clues": record["clues"], "difficulty": record["difficulty"],
                "seed": seed, "time_limit": time_limit, "run_id": run_id}
        for repeat in range(1, repeats + 1):
            ordered = plans.copy()
            random.Random(f"{seed}:{record['puzzle_number']}:{repeat}").shuffle(ordered)
            for method, encoding in ordered:
                row = {**base, "repeat": repeat, "method": method, "encoding": encoding,
                       "solver": sat_solver if method == "sat" else SOLVER_LABELS[method]}
                if record["error"] or record["grid"] is None:
                    row.update(status="INVALID_INPUT", error=record["error"] or "De rong")
                else:
                    row.update(run_trial(record["grid"], method, encoding, sat_solver, time_limit, seed))
                rows.append(result_values(row))
                if not quiet:
                    times = ""
                    if "total_seconds" in row:
                        times = (f" | build={row['build_seconds']:.6f}s"
                                 f" solve={row['solve_seconds']:.6f}s total={row['total_seconds']:.6f}s")
                    print(f"De {record['puzzle_number']} ({size}x{size}) lan {repeat} "
                          f"{method}{('/' + encoding) if encoding else ''}: {row['status']}{times}", flush=True)
                    if row.get("error"):
                        print("  " + row["error"], flush=True)
    return rows

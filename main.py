"""Chay de da chon, noi ket qua cac dot va cap nhat CSV tong hop."""

import os
from contextlib import contextmanager
from pathlib import Path

from src.benchmark import run_benchmark
from src.input import read_dataset

DATASET = "sat_only"  # "mixed" or "sat_only"
SIZES = [9]
INPUT_DIR = None  # None -> data/<DATASET>; 
RESULT_DIR = None  # None -> results/<DATASET>; 
INPUT_FILE = None  # None -> data/<DATASET>/<size>x<size>/generated.csv 
PUZZLE_NUMBERS = list(range(1, 10001))  # None -> all; list -> đề tự chọn

# "sat", "cp-sat", "cplex-mip", "gurobi-mip", "cplex-cp" 
METHODS = ["sat", "cp-sat", "cplex-mip", "gurobi-mip", "cplex-cp"]
SAT_SOLVER = "glucose3"
ENCODINGS = ["pairwise", "seqcounter", "bitwise", "commander", "product"]
TIME_LIMIT = 30  # Giới hạn thời gian cho build + solve; None nếu không giới hạn
REPEATS = 1
SEED = 42  # Benchmark seed


def input_paths(input_file=None):
    directory = Path(__file__).resolve().parent
    if DATASET not in {"mixed", "sat_only"}:
        raise ValueError("DATASET phai la mixed hoac sat_only")
    selected = INPUT_FILE if input_file is None else input_file
    if selected is None:
        if not SIZES or len(set(SIZES)) != len(SIZES) or any(type(size) is not int or size < 1 for size in SIZES):
            raise ValueError("SIZES phai la danh sach kich thuoc nguyen duong, khong trung")
        root = directory / (INPUT_DIR or f"data/{DATASET}")
        return read_dataset(root, SIZES, expected_mode=DATASET)
    paths = [selected] if isinstance(selected, (str, Path)) else list(selected)
    return [directory / path for path in paths]


def result_paths():
    root = Path(__file__).resolve().parent / (RESULT_DIR or f"results/{DATASET}")
    return root / "ket_qua.csv", root / "tong_hop.csv", root


@contextmanager
def _local_cp_optimizer(directory):
    """Use the project's engine and DLLs only during this benchmark run."""
    executable = directory / "tools/cpoptimizer/bin/x64_win64/cpoptimizer.exe"
    dll_directory = directory / "tools/cplex/bin/x64_win64"
    if ("cplex-cp" not in METHODS or os.environ.get("CP_OPTIMIZER_EXECUTABLE")
            or not executable.is_file() or not dll_directory.is_dir()):
        yield
        return

    previous_executable = os.environ.get("CP_OPTIMIZER_EXECUTABLE")
    previous_path = os.environ.get("PATH")
    os.environ["CP_OPTIMIZER_EXECUTABLE"] = str(executable)
    os.environ["PATH"] = str(dll_directory) + os.pathsep + (previous_path or "")
    try:
        yield
    finally:
        for name, previous in (("CP_OPTIMIZER_EXECUTABLE", previous_executable),
                               ("PATH", previous_path)):
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def main(input_file=None):
    directory = Path(__file__).resolve().parent
    inputs = input_paths(input_file)
    output, summary, size_summary_dir = result_paths()
    with _local_cp_optimizer(directory):
        return run_benchmark(inputs,
                             output, summary,
                             puzzle_numbers=PUZZLE_NUMBERS, methods=METHODS,
                             encodings=ENCODINGS, sat_solver=SAT_SOLVER,
                             repeats=REPEATS, time_limit=TIME_LIMIT, seed=SEED,
                             size_summary_dir=size_summary_dir)


if __name__ == "__main__":
    main()

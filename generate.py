"""Generate Sudoku datasets; benchmark configuration is independent in main.py."""

import csv
import json
import math
import random
import tempfile
from pathlib import Path
from threading import Event, Timer
from time import perf_counter
from uuid import uuid4

from pysat.solvers import Solver

from src.analysis import _publish_csvs
from src.encoding import decode_model, encode_sudoku, variable
from src.sudoku import check_solution, units
from src.input import read_dataset, file_sha256 as _sha256

GENERATION_MODE = "sat_only"  # "mixed" / "sat_only"
OUTPUT_DIR = None  # None -> data/<GENERATION_MODE>
SIZES = [9]
SEED = 42
OVERWRITE = True

# Counts per group PER SIZE. 0 -> skip 
COUNTS = {
    "sat_dense": 200,
    "sat_sparse": 200,
    "sat_unique": 200,
    "unsat_direct": 200,
    "unsat_indirect": 200,
}
DENSE_CLUE_RATIOS = (0.60, 0.80)
SPARSE_CLUE_RATIOS = (0.10, 0.30)
UNIQUE_GENERATION_SECONDS = 0.5  # Per candidate, includes build; no hard preemption of build

# GENERATION_MODE = "sat_only" 
COUNT_PER_SIZE = 2500  # Per size AND clue ratio
CLUE_RATIOS = [0.2, 0.4, 0.6, 0.8]


def _validate_size(size):
    if type(size) is not int or size < 4 or math.isqrt(size) ** 2 != size:
        raise ValueError("size phai la 4, 9, 16, 25, ...")


def random_solution(size, rng):
    """Shuffle symbols, bands/stacks, rows/columns within them and transpose."""
    _validate_size(size)
    block = math.isqrt(size)

    def shuffled(values):
        values = list(values)
        rng.shuffle(values)
        return values

    rows = [band * block + row for band in shuffled(range(block))
            for row in shuffled(range(block))]
    columns = [stack * block + column for stack in shuffled(range(block))
               for column in shuffled(range(block))]
    symbols = shuffled(range(1, size + 1))
    solution = [[symbols[(block * (row % block) + row // block + column) % size]
                 for column in columns] for row in rows]
    if rng.randrange(2):
        solution = [list(row) for row in zip(*solution)]
    if not check_solution([[0] * size for _ in range(size)], solution):
        raise RuntimeError("Loi noi bo: bang hoan chinh khong hop le")
    return solution


def _validate_generation(sizes, count_per_size, clue_ratios, seed):
    if not sizes or len(set(sizes)) != len(sizes):
        raise ValueError("sizes phai khac nhau va khong rong")
    for size in sizes:
        _validate_size(size)
    if (type(count_per_size) is not int or count_per_size < 1
            or type(seed) is not int or not 0 <= seed <= 2147483647):
        raise ValueError("count_per_size phai duong; seed phai trong 0..2147483647")
    if not clue_ratios or any(not math.isfinite(ratio) or not 0 < ratio <= 1 for ratio in clue_ratios):
        raise ValueError("clue_ratios phai trong (0,1]")
    profiles = {}
    for size in sizes:
        clue_counts = [int(size * size * ratio + 0.5) for ratio in clue_ratios]
        if any(clues < 1 for clues in clue_counts):
            raise ValueError("Moi profile phai co it nhat mot o cho truoc")
        if len(set(clue_counts)) != len(clue_counts):
            raise ValueError("Cac ratio phai tao so clues khac nhau")
        profiles[size] = clue_counts
    return profiles


def generate_dataset(output_path, sizes=(9,), count_per_size=10, clue_ratios=(0.4,), seed=42, overwrite=False):
    """count_per_size de cho moi cap size/ratio. Chua kiem tra nghiem duy nhat."""
    sizes, clue_ratios = list(sizes), list(clue_ratios)
    profiles = _validate_generation(sizes, count_per_size, clue_ratios, seed)
    path = Path(output_path)
    if path.suffix.lower() != ".csv":
        raise ValueError("File sinh de phai la CSV")
    if path.exists() and not overwrite:
        raise FileExistsError(f"File da ton tai: {path}")
    rng, records, seen = random.Random(seed), [], set()
    for size in sizes:
        for clues in profiles[size]:
            group = f"generated_{size}x{size}_clues{clues}"
            for number in range(1, count_per_size + 1):
                for attempt in range(100):
                    solution = random_solution(size, rng)
                    selected = set(rng.sample(range(size * size), clues))
                    grid = [[value if r * size + c in selected else 0
                             for c, value in enumerate(row)] for r, row in enumerate(solution)]
                    digest = tuple(value for row in grid for value in row)
                    if digest not in seen:
                        seen.add(digest)
                        break
                else:
                    raise ValueError(f"Khong sinh du de khac nhau cho {group}")
                values = [str(value) for row in grid for value in row]
                records.append({"id": f"{group}_{number}", "size": size,
                                "puzzle": "".join(values) if size <= 9 else " ".join(values),
                                "clues": clues, "dataset_group": group, "seed": seed,
                                "unique": "unknown"})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "size", "puzzle", "clues", "dataset_group", "seed", "unique"])
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def generate_by_size(output_dir, sizes=(9, 16, 25), count_per_size=10,
                     clue_ratios=(0.4, 0.6), seed=42, overwrite=False):
    """Moi kich thuoc co mot CSV; cung seed tao cung de khi sinh rieng."""
    sizes, clue_ratios = list(sizes), list(clue_ratios)
    _validate_generation(sizes, count_per_size, clue_ratios, seed)
    paths = {}
    for size in sizes:
        path = Path(output_dir) / f"{size}x{size}" / "generated.csv"
        if path.exists() and not overwrite:
            raise FileExistsError(f"File da ton tai: {path}")
        paths[size] = path
    return {
        size: generate_dataset(path, sizes=[size], count_per_size=count_per_size,
                               clue_ratios=clue_ratios, seed=seed, overwrite=overwrite)
        for size, path in paths.items()
    }


def has_direct_conflict(grid):
    """Duplicate givens in a row, column or block; absence does not imply SAT."""
    for coordinates in units(len(grid)):
        values = [grid[r][c] for r, c in coordinates if grid[r][c]]
        if len(values) != len(set(values)):
            return True
    return False


def _planted(size, rng, low, high):
    solution = random_solution(size, rng)
    count = max(1, round(size * size * rng.uniform(low, high)))
    selected = set(rng.sample(range(size * size), count))
    grid = [[solution[r][c] if r * size + c in selected else 0
             for c in range(size)] for r in range(size)]
    return grid


def _blocked_cell(size, rng):
    """A forced missing row value blocked in its column, without duplicate givens."""
    grid = [[0] * size for _ in range(size)]
    r = rng.randrange(size)
    c = rng.randrange(size)
    other_row = rng.choice([index for index in range(size) if index != r])
    symbols = list(range(1, size + 1))
    rng.shuffle(symbols)
    grid[r] = symbols
    missing = grid[r][c]
    grid[r][c] = 0
    grid[other_row][c] = missing
    return grid


def _unique_reduction(size, rng, time_limit=0.5):
    """Remove clues only after proving no alternate solution, with a bounded search.

    The known solution is excluded by one blocking clause. An UNSAT call under
    the remaining clues proves that the removal preserves uniqueness. A search
    limit keeps the clue; it never counts as a uniqueness proof.
    """
    started = perf_counter()
    grid = random_solution(size, rng)
    cnf = encode_sudoku([[0] * size for _ in range(size)])
    with Solver(name="glucose3", bootstrap_with=cnf.clauses) as solver:
        remaining = time_limit - (perf_counter() - started)
        if remaining <= 0:
            return grid
        expired = Event()

        def interrupt():
            expired.set()
            solver.interrupt()

        timer = Timer(remaining, interrupt)
        timer.daemon = True
        timer.start()
        try:
            # Sample beyond the cyclic solution family used by random_solution.
            phases = []
            for r in range(size):
                for c in range(size):
                    chosen = rng.randint(1, size)
                    phases.extend(variable(size, r, c, value) * (1 if value == chosen else -1)
                                  for value in range(1, size + 1))
            solver.set_phases(phases)
            sampled = solver.solve_limited(expect_interrupt=True)
            if sampled is not True:
                return grid  # The fallback complete grid has exactly one solution.
            grid = decode_model(size, solver.get_model())
            if not check_solution([[0] * size for _ in range(size)], grid):
                raise RuntimeError("Invalid full grid in uniqueness generation")
            clues = {r * size + c: variable(size, r, c, grid[r][c])
                     for r in range(size) for c in range(size)}
            solver.add_clause([-literal for literal in clues.values()])
            cells = list(clues)
            rng.shuffle(cells)
            for cell in cells:
                if expired.is_set():
                    break
                literal = clues.pop(cell)
                alternative = solver.solve_limited(assumptions=list(clues.values()), expect_interrupt=True)
                if alternative is False:
                    r, c = divmod(cell, size)
                    grid[r][c] = 0
                else:
                    clues[cell] = literal
                    if alternative is None:
                        break
        finally:
            timer.cancel()
            timer.join()
            solver.clear_interrupt()
    return grid


GROUPS = ("sat_dense", "sat_sparse", "sat_unique", "unsat_direct", "unsat_indirect")
DATA_FIELDS = ["id", "size", "puzzle", "clues", "dataset_group", "seed", "unique",
               "category", "expected_status"]


def generation_settings():
    """Collect only the dataset generation settings."""
    return dict(mode=GENERATION_MODE, counts=COUNTS, seed=SEED,
                dense_ratios=DENSE_CLUE_RATIOS, sparse_ratios=SPARSE_CLUE_RATIOS,
                unique_seconds=UNIQUE_GENERATION_SECONDS,
                count_per_size=COUNT_PER_SIZE, clue_ratios=CLUE_RATIOS)


def dataset_directory():
    return Path(__file__).resolve().parent / (OUTPUT_DIR or f"data/{GENERATION_MODE}")


def _generation_config(sizes, mode, counts, seed, dense_ratios, sparse_ratios,
                       unique_seconds, count_per_size, clue_ratios):
    if mode not in {"mixed", "sat_only"}:
        raise ValueError("GENERATION_MODE phai la mixed hoac sat_only")
    _validate_generation(sizes, 1, [0.5], seed)
    if mode == "sat_only":
        _validate_generation(sizes, count_per_size, clue_ratios, seed)
        return dict(mode=mode, seed=seed, count_per_size=count_per_size, clue_ratios=list(clue_ratios))
    if not counts or set(counts) - set(GROUPS):
        raise ValueError(f"COUNTS chi nhan cac nhom: {GROUPS}")
    if any(type(count) is not int or count < 0 for count in counts.values()) or not any(counts.values()):
        raise ValueError("COUNTS phai la so nguyen khong am, it nhat mot nhom > 0")
    for ratios in (dense_ratios, sparse_ratios):
        if len(ratios) != 2 or any(isinstance(value, bool) or not isinstance(value, (int, float))
                                  or not math.isfinite(value) for value in ratios):
            raise ValueError("Moi khoang mat do can hai so huu han")
        if not 0 < ratios[0] <= ratios[1] <= 1:
            raise ValueError("Khoang mat do phai thoa 0 < min <= max <= 1")
    if (isinstance(unique_seconds, bool) or not isinstance(unique_seconds, (int, float))
            or not math.isfinite(unique_seconds) or unique_seconds <= 0):
        raise ValueError("UNIQUE_GENERATION_SECONDS phai duong, huu han")
    return dict(mode=mode, seed=seed, counts={group: counts.get(group, 0) for group in GROUPS},
                dense_ratios=list(dense_ratios), sparse_ratios=list(sparse_ratios),
                unique_seconds=unique_seconds)


def _mixed_rows(size, config):
    rng = random.Random(f"{config['seed']}:{size}")
    seen, rows = set(), []
    for category in GROUPS:
        for number in range(1, config["counts"][category] + 1):
            for _ in range(100):
                if category in {"sat_dense", "sat_sparse"}:
                    ratios = config["dense_ratios" if category == "sat_dense" else "sparse_ratios"]
                    grid = _planted(size, rng, *ratios)
                elif category == "sat_unique":
                    grid = _unique_reduction(size, rng, config["unique_seconds"])
                elif category == "unsat_direct":
                    grid = _planted(size, rng, *config["sparse_ratios"])
                    r = rng.randrange(size)
                    left, right = rng.sample(range(size), 2)
                    grid[r][left] = grid[r][right] = rng.randint(1, size)
                else:
                    grid = _blocked_cell(size, rng)
                digest = tuple(value for row in grid for value in row)
                if digest not in seen:
                    seen.add(digest)
                    break
            else:
                raise ValueError(f"Khong sinh du de khac nhau cho {size}x{size}/{category}")
            values = [str(value) for row in grid for value in row]
            unsat = category.startswith("unsat_")
            rows.append({
                "id": f"mixed_{size}x{size}_{category}_{number}", "size": size,
                "puzzle": "".join(values) if size <= 9 else " ".join(values),
                "clues": sum(value != 0 for row in grid for value in row),
                "dataset_group": f"mixed_{size}x{size}_{category}", "seed": config["seed"],
                "unique": "false" if unsat else "true" if category == "sat_unique" else "unknown",
                "category": category, "expected_status": "UNSAT" if unsat else "SAT",
            })
    # Mix categories so a short prefix is not just dense SAT puzzles.
    rng.shuffle(rows)
    return rows


def generate_experiment(output_dir, sizes=(9, 16, 25), mode="mixed", counts=None, seed=42,
                        dense_ratios=(0.60, 0.85), sparse_ratios=(0.10, 0.35),
                        unique_seconds=0.5, count_per_size=10, clue_ratios=(0.2, 0.4, 0.6, 0.8),
                        overwrite=False, quiet=False):
    """Publish the selected CSVs and manifest together; keep the old set on failure."""
    sizes = list(sizes)
    if counts is None:
        counts = {group: 10 for group in GROUPS}
    config = _generation_config(sizes, mode, counts, seed, dense_ratios, sparse_ratios,
                                 unique_seconds, count_per_size, clue_ratios)
    root = Path(output_dir).resolve()
    manifest_path = root / "dataset.json"
    targets = {size: root / f"{size}x{size}" / "generated.csv" for size in sizes}
    for path in [manifest_path, *targets.values()]:
        if path.exists() and not overwrite:
            raise FileExistsError(f"Da co {path}; doi OUTPUT_DIR hoac dat OVERWRITE = True")
    retained = []
    if manifest_path.is_file():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if previous.get("format_version") != 1 or previous.get("state") != "complete":
            raise ValueError("dataset.json cu khong hop le; chon OUTPUT_DIR khac")
        if previous.get("config", {}).get("mode") != mode:
            raise ValueError("OUTPUT_DIR dang chua loai du lieu khac; chon thu muc rieng cho moi mode")
        for item in previous.get("files", []):
            if item["size"] not in targets:
                retained.append({**item,
                                 "config": item.get("config", previous["config"]),
                                 "generation_id": item.get("generation_id", previous.get("generation_id"))})
    root.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    manifest = dict(format_version=1, state="complete", generation_id=uuid4().hex,
                    config=config, files=retained)
    with tempfile.TemporaryDirectory(prefix=".generate-", dir=root) as temporary:
        stage = Path(temporary)
        copies = {}
        for size, target in targets.items():
            staged = stage / f"{size}.csv"
            if mode == "sat_only":
                generate_dataset(staged, sizes=[size], count_per_size=count_per_size,
                                 clue_ratios=clue_ratios, seed=seed)
            else:
                rows = _mixed_rows(size, config)
                with staged.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=DATA_FIELDS)
                    writer.writeheader()
                    writer.writerows(rows)
            with staged.open(encoding="utf-8", newline="") as stream:
                row_count = sum(1 for _ in csv.DictReader(stream))
            manifest["files"].append(dict(size=size, path=target.relative_to(root).as_posix(),
                                          rows=row_count, sha256=_sha256(staged),
                                          config=config, generation_id=manifest["generation_id"]))
            copies[target] = staged
            if not quiet:
                print(f"Da tao {row_count} de {size}x{size}; dang chuan bi luu bo du lieu", flush=True)
        manifest["elapsed_seconds"] = perf_counter() - started
        staged_manifest = stage / "dataset.json"
        staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        copies[manifest_path] = staged_manifest
        _publish_csvs({}, copies)
    if not quiet:
        print(f"Da luu {sum(item['rows'] for item in manifest['files'] if item['size'] in targets)} de moi: {root}")
        print(f"Danh sach va ma kiem tra du lieu: {manifest_path}")
    return manifest


def main():
    root = dataset_directory()
    manifest = generate_experiment(root, sizes=SIZES, **generation_settings(), overwrite=OVERWRITE)
    return sum(item["rows"] for item in manifest["files"] if item["size"] in SIZES)


if __name__ == "__main__":
    main()

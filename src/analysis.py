"""Tong hop so de, trang thai va thoi gian theo phuong phap/encoding."""

import csv
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from uuid import uuid4

TIMES = ("build_seconds", "solve_seconds", "total_seconds")


def _sat(row):
    return row["status"] == "SAT" and row["verified"].lower() == "true"


def _success(row):
    return _sat(row) and all(row[field] for field in TIMES)


def _summary_rows(rows, run_id, run_state, plans=None, repeats=None):
    """Calculate one run or the cumulative view directly from trial rows."""
    repeats_by_run = defaultdict(lambda: repeats or 1)
    for row in rows:
        identifier = row.get("run_id", "")
        repeats_by_run[identifier] = max(repeats_by_run[identifier], int(row["repeat"]))
    groups = defaultdict(list)
    groups["all", "ALL", "ALL"] = rows
    for row in rows:
        groups["size", "ALL", row["size"]].append(row)
        groups["group", row["dataset_group"], row["size"]].append(row)
    summary = []
    for (scope, group, size), trials in sorted(
            groups.items(), key=lambda item: (item[0][0], item[0][1],
                                             int(item[0][2]) if item[0][2] != "ALL" else 0)):
        by_method, by_puzzle = defaultdict(list), defaultdict(dict)
        for row in trials:
            label = row["method"], row["encoding"]
            puzzle = row.get("run_id", ""), row["source"], row["puzzle_number"]
            by_method[label].append(row)
            by_puzzle[puzzle][label, int(row["repeat"])] = row
        group_plans = plans if plans is not None else sorted(by_method)
        common = [puzzle for puzzle, lookup in by_puzzle.items()
                  if all((label, repeat) in lookup and _success(lookup[label, repeat])
                         for label in group_plans for repeat in range(1, repeats_by_run[puzzle[0]] + 1))]
        for (method, encoding), method_rows in sorted(by_method.items()):
            statuses = Counter(row["status"] for row in method_rows)
            successful = [row for row in method_rows if _success(row)]
            outcomes = defaultdict(set)
            for row in method_rows:
                key = row.get("run_id", ""), row["source"], row["puzzle_number"]
                outcomes[key].add("SAT" if _sat(row) else row["status"] if row["status"] != "SAT" else "ERROR")
            sat_puzzles = sum("SAT" in states and "UNSAT" not in states for states in outcomes.values())
            unsat_puzzles = sum("UNSAT" in states and "SAT" not in states for states in outcomes.values())
            inconsistent = sum({"SAT", "UNSAT"} <= states for states in outcomes.values())
            timed = [row for row in method_rows if all(row[field] for field in TIMES)]
            elapsed = [float(row["elapsed_seconds"]) for row in method_rows if row.get("elapsed_seconds")]
            item = {"run_id": run_id, "run_state": run_state,
                    "scope": scope, "dataset_group": group, "size": size, "method": method,
                    "solver": method_rows[0]["solver"], "encoding": encoding,
                    "puzzles": len(outcomes), "runs": len(method_rows),
                    "sat_puzzles": sat_puzzles, "unsat_puzzles": unsat_puzzles,
                    "unresolved_puzzles": len(outcomes) - sat_puzzles - unsat_puzzles - inconsistent,
                    "inconsistent_puzzles": inconsistent,
                    "sat": sum(_sat(row) for row in method_rows), "unsat": statuses["UNSAT"],
                    "timeout": statuses["TIMEOUT"], "unknown": statuses["UNKNOWN"],
                    "unavailable": statuses["UNAVAILABLE"], "error": statuses["ERROR"],
                    "invalid_input": statuses["INVALID_INPUT"], "common_puzzles": len(common),
                    "timed_runs": len(timed), "untimed_runs": len(method_rows) - len(timed),
                    "elapsed_runs": len(elapsed), "elapsed_seconds_sum": sum(elapsed) if elapsed else ""}
            for field in TIMES:
                # Include every measured outcome, including UNSAT and TIMEOUT.
                item[field + "_sum"] = sum(float(row[field]) for row in timed) if timed else ""
                values = [float(row[field]) for row in successful]
                item[field + "_mean"] = mean(values) if values else ""
                item[field + "_median"] = median(values) if values else ""
                common_values = [median(float(by_puzzle[puzzle][(method, encoding), repeat][field])
                                        for repeat in range(1, repeats_by_run[puzzle[0]] + 1)) for puzzle in common]
                item["common_" + field + "_mean"] = mean(common_values) if common_values else ""
            for field in ("variables", "clauses", "constraints"):
                values = [float(row[field]) for row in successful if row[field]]
                item[field + "_mean"] = mean(values) if values else ""
            summary.append(item)
    fields = ["run_id", "run_state", "scope", "dataset_group", "size", "method", "solver", "encoding", "puzzles", "runs",
              "sat_puzzles", "unsat_puzzles", "unresolved_puzzles", "inconsistent_puzzles",
              "sat", "unsat", "timeout", "unknown", "unavailable", "error", "invalid_input",
              "common_puzzles", "timed_runs", "untimed_runs", "elapsed_runs", "elapsed_seconds_sum"]
    fields += [key for field in TIMES for key in
               (field + "_sum", field + "_mean", field + "_median", "common_" + field + "_mean")]
    fields += ["variables_mean", "clauses_mean", "constraints_mean"]
    return fields, summary


def _write_summary_rows(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: f"{value:.9f}" if isinstance(value, float) else value
                             for key, value in row.items()})


def _temporary_path(target):
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp",
                                       dir=target.parent)
    os.close(descriptor)
    return Path(name)


def _publish_csvs(tables, copies):
    """Stage every CSV first; restore the previous snapshot on a publish error."""
    targets = list(tables) + list(copies)
    if len({path.resolve() for path in targets}) != len(targets):
        raise ValueError("Cac file CSV ket qua phai co duong dan khac nhau")
    staged, backups, published = {}, {}, []
    committed = False
    try:
        for target in targets:
            temporary = _temporary_path(target)
            staged[target] = temporary
            if target in tables:
                fields, rows = tables[target]
                _write_summary_rows(temporary, fields, rows)
            else:
                shutil.copyfile(copies[target], temporary)
            if target.exists():
                backup = _temporary_path(target)
                backups[target] = backup
                shutil.copyfile(target, backup)
        for target, temporary in staged.items():
            os.replace(temporary, target)
            published.append(target)
        committed = True
    except BaseException:
        while published:
            target = published[-1]
            if target in backups:
                os.replace(backups[target], target)
            else:
                target.unlink()
            published.pop()
        raise
    finally:
        for temporary in staged.values():
            temporary.unlink(missing_ok=True)
        for target, backup in backups.items():
            if committed or target not in published:
                backup.unlink(missing_ok=True)


def _read_detail(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = list(reader.fieldnames or []), list(reader)
    required = {"source", "puzzle_number", "method", "encoding", "repeat", "status",
                "verified", "size", "dataset_group", "solver", *TIMES,
                "variables", "clauses", "constraints"}
    if not required <= set(fields):
        raise ValueError(f"CSV chi tiet thieu cot can thiet de tong hop: {path}")
    return fields, rows


def _trial_key(row):
    return tuple(str(row.get(key, "")) for key in
                 ("run_id", "source", "puzzle_number", "method", "encoding", "repeat"))


def _merge_rows(*batches):
    """Root and per-size CSVs contain copies of the same trials, counted once."""
    merged = {}
    for batch in batches:
        for row in batch:
            key = _trial_key(row)
            if key not in merged:
                merged[key] = row.copy()
                continue
            previous = merged[key]
            for field, value in row.items():
                if previous.get(field, "") not in ("", value) and value != "":
                    raise ValueError(f"Hai CSV co so lieu khac nhau cho cung luot chay: {key}")
                if value != "":
                    previous[field] = value
    return list(merged.values())


def _read_collection(result_path, summary_path, root=None):
    """Read fixed CSVs only; retain the union of root and per-size results."""
    fields, rows, states = [], [], {}
    legacy_id = uuid4().hex

    def read_pair(detail, summary, size=None):
        nonlocal fields, rows
        if not detail.is_file():
            return
        detail_fields, batch = _read_detail(detail)
        fields = list(dict.fromkeys(fields + detail_fields + ["run_id"]))
        if size is not None and any(row["size"] != size for row in batch):
            raise ValueError(f"CSV chua kich thuoc khong dung thu muc: {detail}")
        for row in batch:
            row["run_id"] = row.get("run_id") or legacy_id
        rows = _merge_rows(rows, batch)
        if summary.is_file():
            with summary.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    if row.get("run_id") and row["run_id"] != "ALL_RUNS" and row.get("run_state"):
                        states[row["run_id"]] = row["run_state"]

    read_pair(Path(result_path), Path(summary_path))
    if root is not None and Path(root).is_dir():
        for folder in sorted(Path(root).iterdir()):
            parts = folder.name.split("x")
            if (folder.is_dir() and len(parts) == 2 and parts[0] == parts[1]
                    and parts[0].isdigit() and int(parts[0]) > 0):
                read_pair(folder / "ket_qua.csv", folder / "tong_hop.csv", parts[0])
    return fields, rows, states


def _summarize_runs(rows, states, overrides=None):
    by_run = defaultdict(list)
    for row in rows:
        by_run[row["run_id"]].append(row)
    summary_rows = []
    for identifier, trials in by_run.items():
        plans, repeats = (overrides or {}).get(identifier, (None, None))
        fields, summary = _summary_rows(trials, identifier, states.get(identifier, "rebuilt"), plans, repeats)
        summary_rows.extend(summary)
    fields, cumulative = _summary_rows(rows, "ALL_RUNS", "cumulative")
    return fields, summary_rows + cumulative


def _collection_tables(result_path, summary_path, root, fields, rows, summary_fields, summary_rows):
    tables = {Path(result_path): (fields, rows), Path(summary_path): (summary_fields, summary_rows)}
    if root is not None:
        sizes = {"9", "16", "25"} | {row["size"] for row in rows if int(row["size"]) > 0}
        for size in sorted(sizes, key=int):
            folder = Path(root) / f"{size}x{size}"
            for name in ("ket_qua.csv", "tong_hop.csv"):
                if (folder / name).resolve() in {Path(result_path).resolve(), Path(summary_path).resolve()}:
                    raise ValueError("CSV chung trung duong dan voi CSV theo kich thuoc")
            tables[folder / "ket_qua.csv"] = fields, [row for row in rows if row["size"] == size]
            tables[folder / "tong_hop.csv"] = summary_fields, [
                row for row in summary_rows if row["scope"] == "size" and row["size"] == size]
    return tables


def _save_result_tables(tables):
    """Write only the fixed CSVs; keep rollback bytes in RAM, without extra files."""
    if len({path.resolve() for path in tables}) != len(tables):
        raise ValueError("Cac file CSV ket qua phai co duong dan khac nhau")
    previous = {}
    try:
        for path, (fields, rows) in tables.items():
            original = path.read_bytes() if path.is_file() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            previous[path] = original
            _write_summary_rows(path, fields, rows)
    except BaseException:
        for path, original in reversed(list(previous.items())):
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise


def append_results(new_rows, result_path, summary_path, size_summary_dir=None, plans=None, repeats=1):
    """Append completed batches, then refresh per-run and cumulative summaries."""
    from .output import CSV_FIELDS

    fields, previous, states = _read_collection(result_path, summary_path, size_summary_dir)
    fields = list(dict.fromkeys(fields + CSV_FIELDS))
    rows = _merge_rows(previous, new_rows)
    overrides = {}
    for row in new_rows:
        states[row["run_id"]] = "complete"
        overrides[row["run_id"]] = plans, repeats
    summary_fields, summary_rows = _summarize_runs(rows, states, overrides)
    tables = _collection_tables(result_path, summary_path, size_summary_dir, fields, rows,
                                summary_fields, summary_rows)
    _save_result_tables(tables)
    return len(summary_rows)


def rebuild_results(result_path, summary_path, size_summary_dir=None, allow_multiple_runs=False):
    """Recalculate fixed CSVs from saved trials, without running any solver."""
    fields, rows, _ = _read_collection(result_path, summary_path, size_summary_dir)
    if not fields:
        raise FileNotFoundError(f"Chua co CSV ket qua: {result_path}")
    if len({row["run_id"] for row in rows}) > 1 and not allow_multiple_runs:
        raise ValueError("CSV chi tiet chua nhieu run_id; dat allow_multiple_runs=True")
    summary_fields, summary_rows = _summarize_runs(rows, {r["run_id"]: "rebuilt" for r in rows})
    tables = _collection_tables(result_path, summary_path, size_summary_dir, fields, rows,
                                summary_fields, summary_rows)
    _save_result_tables(tables)
    return len(summary_rows)

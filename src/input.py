"""Read Sudoku datasets"""

import csv
import hashlib
import json
from math import isqrt
from pathlib import Path

from .sudoku import validate_grid



def decode_puzzle(text, size=None):
    text = text.strip()
    if not text:
        raise ValueError("De Sudoku rong")
    if size is not None and (type(size) is not int or size < 1):
        raise ValueError("Kich thuoc Sudoku phai la so nguyen duong")

    separated = any(character.isspace() for character in text)
    tokens = text.split() if separated else list(text)
    size = size if size is not None else isqrt(len(tokens))
    if len(tokens) != size * size:
        raise ValueError("So o trong chuoi khong tao thanh bang NxN")
    if size > 9 and not separated:
        raise ValueError("De lon hon 9x9 can cac so cach nhau bang khoang trang")

    values = [0 if token == "." else int(token) for token in tokens]
    grid = [values[start:start + size] for start in range(0, len(values), size)]
    validate_grid(grid)
    return grid


def _selected_numbers(puzzle_numbers):
    if puzzle_numbers is None:
        return None
    numbers = list(puzzle_numbers)
    if not numbers or any(type(number) is not int or number < 1 for number in numbers):
        raise ValueError("PUZZLE_NUMBERS phai chua cac so nguyen tu 1 tro len")
    return set(numbers)


def _record(path, number, row=None):
    row = row or {}
    return {
        "puzzle_number": number,
        "puzzle_id": str(row.get("id") or "").strip() or str(number),
        "grid": None,
        "size": "",
        "clues": "",
        "difficulty": str(row.get("difficulty") or ""),
        "dataset_group": str(row.get("dataset_group") or "").strip() or Path(path).stem,
        "error": "",
    }


def _fill_grid(record, grid):
    record["size"] = validate_grid(grid)
    record["clues"] = sum(value != 0 for row in grid for value in row)
    record["grid"] = grid
    return record


def iter_puzzle_records(path, puzzle_numbers=None):
    """Yield metadata and grids, continuing after a malformed selected row.

    Row numbers start at 1 after a dataset header; a matrix has one puzzle.
    ``None`` selects all rows. Missing selected numbers become error records.
    Reference columns such as ``solution`` are deliberately ignored.
    """
    wanted = _selected_numbers(puzzle_numbers)
    pending = None if wanted is None else set(wanted)
    try:
        file = open(path, newline="", encoding="utf-8-sig")
    except OSError as exc:
        record = _record(path, 1)
        record["error"] = f"Khong doc duoc file CSV: {exc}"
        yield record
        return

    with file:
        reader = csv.reader(file, strict=True)
        try:
            first_row = next(reader, None)
        except (csv.Error, UnicodeError) as exc:
            record = _record(path, 1)
            record["error"] = f"Header CSV khong hop le: {exc}"
            yield record
            return
        if not first_row:
            record = _record(path, 1)
            record["error"] = "File CSV rong hoac header rong"
            yield record
            return

        headers = [cell.strip().lower() for cell in first_row]
        if "puzzle" in headers:
            if len(headers) != len(set(headers)) or any(not header for header in headers):
                record = _record(path, 1)
                record["error"] = "Header CSV co cot trung ten hoac ten cot rong"
                yield record
                return
            number = 0
            csv_failed = False
            try:
                for number, cells in enumerate(reader, start=1):
                    if wanted is not None and number not in wanted:
                        continue
                    if pending is not None:
                        pending.remove(number)
                    row = dict(zip(headers, cells))
                    record = _record(path, number, row)
                    try:
                        if len(cells) != len(headers):
                            raise ValueError("Dong CSV khong khop voi header")
                        declared_size = str(row.get("size") or "").strip()
                        size = int(declared_size) if declared_size else None
                        if size is not None:
                            record["size"] = size
                        else:
                            text = row["puzzle"].strip()
                            token_count = len(text.split()) if any(c.isspace() for c in text) else len(text)
                            inferred_size = isqrt(token_count)
                            if inferred_size and inferred_size * inferred_size == token_count:
                                record["size"] = inferred_size
                        grid = decode_puzzle(row["puzzle"], size)
                        _fill_grid(record, grid)
                    except (ValueError, TypeError, KeyError) as exc:
                        record["error"] = str(exc)
                    yield record
                    if pending is not None and not pending:
                        return
            except (csv.Error, UnicodeError) as exc:
                csv_failed = True
                # Broken quoting/encoding cannot be resynchronized safely.
                next_number = number + 1
                if wanted is None or next_number in pending:
                    record = _record(path, next_number)
                    record["error"] = f"Khong doc duoc dong CSV: {exc}"
                    yield record
                    if pending is not None:
                        pending.remove(next_number)
            if number == 0 and wanted is None and not csv_failed:
                record = _record(path, 1)
                record["error"] = "Dataset CSV chi co header, khong co de Sudoku"
                yield record
        else:
            # Without a puzzle column, interpret the file as one numeric matrix.
            record = _record(path, 1)
            record["size"] = len(first_row)
            if wanted is None or 1 in wanted:
                try:
                    grid = [[0 if cell.strip() in {"", "."} else int(cell) for cell in first_row]]
                    for cells in reader:
                        if len(grid) >= record["size"]:
                            raise ValueError("File ma tran co qua nhieu dong")
                        grid.append([0 if cell.strip() in {"", "."} else int(cell) for cell in cells])
                    _fill_grid(record, grid)
                except (csv.Error, UnicodeError, ValueError, TypeError) as exc:
                    record["error"] = f"Ma tran CSV khong hop le (hoac thieu cot puzzle): {exc}"
                yield record
                if pending is not None:
                    pending.discard(1)

    for number in sorted(pending or []):
        record = _record(path, number)
        record["error"] = f"Khong tim thay de thu {number} trong file CSV"
        yield record


def file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_dataset(output_dir, sizes, expected_config=None, expected_mode=None):
    """Select CSVs by size; check available manifest metadata without requiring it."""
    root = Path(output_dir).resolve()
    manifest_path = root / "dataset.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file() else None)
    if manifest is None and expected_config is not None:
        raise FileNotFoundError(f"Chua co {manifest_path}; khong the kiem tra config sinh")
    if manifest is not None and (manifest.get("format_version") != 1 or manifest.get("state") != "complete"):
        raise ValueError("Bo du lieu chua hoan tat hoac sai dinh dang dataset.json")
    if manifest is not None and expected_mode is not None and manifest.get("config", {}).get("mode") != expected_mode:
        raise ValueError(f"Bo du lieu trong dataset.json khong phai {expected_mode}; kiem tra DATASET/INPUT_DIR trong main.py")
    manifest = manifest or {}
    imported_sat = (manifest.get("origin") == "imported"
                    and manifest.get("config", {}).get("mode") == "sat_only"
                    and expected_config is not None and expected_config.get("mode") == "sat_only")
    files = manifest.get("files", [])
    if len({item["size"] for item in files}) != len(files):
        raise ValueError("dataset.json co kich thuoc trung nhau")
    by_size = {item["size"]: item for item in files}
    paths = []
    for size in sizes:
        expected_path = f"{size}x{size}/generated.csv"
        item = by_size.get(size)
        if item is not None and item["path"] != expected_path:
            raise ValueError(f"Duong dan trong dataset.json khong dung cho {size}x{size}")
        if expected_config is not None and not imported_sat:
            actual_config = item.get("config", manifest.get("config")) if item else None
            if actual_config != expected_config:
                raise ValueError("Config generate.py khac bo da sinh; khoi phuc config hoac sinh bo moi")
        path = root / expected_path
        if not path.is_file():
            raise FileNotFoundError(f"Thieu CSV da sinh: {path}")
        if item is not None and file_sha256(path) != item["sha256"]:
            raise ValueError(f"CSV da bi thay doi so voi dataset.json: {path}")
        paths.append(path)
    return paths

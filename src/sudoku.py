from math import isqrt


def validate_grid(grid):
    size = len(grid)
    if size < 4 or isqrt(size) ** 2 != size:
        raise ValueError("Kich thuoc Sudoku phai la 4, 9, 16, 25, ...")
    if any(len(row) != size for row in grid):
        raise ValueError(f"Bang phai co {size} hang va {size} cot")
    if any(type(value) is not int or not 0 <= value <= size for row in grid for value in row):
        raise ValueError(f"Moi o phai la so nguyen tu 0 den {size}; 0 la o trong")
    return size


def units(size):
    """Moi nhom la toa do (hang, cot) cua mot hang, cot hoac khoi."""
    for row in range(size):
        yield [(row, column) for column in range(size)]
    for column in range(size):
        yield [(row, column) for row in range(size)]
    block = isqrt(size)
    for first_row in range(0, size, block):
        for first_column in range(0, size, block):
            yield [
                (row, column)
                for row in range(first_row, first_row + block)
                for column in range(first_column, first_column + block)
            ]


def check_solution(puzzle, solution):
    if solution is None:
        return False
    try:
        size = validate_grid(puzzle)
        if validate_grid(solution) != size:
            return False
    except (TypeError, ValueError):
        return False

    expected = set(range(1, size + 1))
    for coordinates in units(size):
        if {solution[row][column] for row, column in coordinates} != expected:
            return False
    return all(
        puzzle[row][column] == 0 or puzzle[row][column] == solution[row][column]
        for row in range(size) for column in range(size)
    )

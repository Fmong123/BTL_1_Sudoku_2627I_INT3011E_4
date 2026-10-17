from pysat.formula import CNF, IDPool
from .cardinality import exactly_one
from .sudoku import units, validate_grid


def variable(size, row, column, value):
    return row * size * size + column * size + value


def encode_sudoku(grid, encoding="seqcounter"):
    size = validate_grid(grid)
    cnf = CNF()
    pool = IDPool(start_from=size ** 3 + 1)  # Biến phụ

    # Exactly one của 1 ô
    for row in range(size):
        for column in range(size):
            literals = [variable(size, row, column, value) for value in range(1, size + 1)]
            for clause in exactly_one(literals, encoding, pool):
                cnf.append(clause)

    # Exactly one của 1 số trong 1 hàng, cột, hoặc khối
    for coordinates in units(size):
        for value in range(1, size + 1):
            literals = [variable(size, row, column, value) for row, column in coordinates]
            for clause in exactly_one(literals, encoding, pool):
                cnf.append(clause)

    # Ô đã được điền sẵn
    for row in range(size):
        for column in range(size):
            if grid[row][column]:
                cnf.append([variable(size, row, column, grid[row][column])])
    return cnf


def decode_model(size, model):
    grid = [[0] * size for _ in range(size)]
    for literal in model:
        if 1 <= literal <= size ** 3:  # Biến chính
            cell, digit = divmod(literal - 1, size)
            row, column = divmod(cell, size)
            if grid[row][column]:
                raise ValueError("SAT model gan nhieu so cho mot o")
            grid[row][column] = digit + 1
    if any(value == 0 for row in grid for value in row):
        raise ValueError("SAT model thieu gia tri cua mot o")
    return grid

"""Sudoku bang bien nguyen va AllDifferent cua IBM CP Optimizer."""

import os
import shutil
from pathlib import Path
from time import perf_counter

from ..sudoku import units, validate_grid
from ._timing import build_timeout, finish_build, finish_info, remaining_budget, start_build


def solve(grid, time_limit=30, seed=42):
    from docplex.cp.config import context
    from docplex.cp.model import CpoModel, all_diff, integer_var

    build_started = start_build(time_limit, seed)
    configured = os.environ.get("CP_OPTIMIZER_EXECUTABLE") or context.solver.local.execfile
    executable = shutil.which(configured) if configured else None
    if not executable and configured and Path(configured).is_file():
        executable = str(Path(configured).resolve())
    if not executable:
        raise FileNotFoundError("Chua co CP Optimizer; cai engine va dat bien CP_OPTIMIZER_EXECUTABLE")

    size = validate_grid(grid)
    model = CpoModel(name="sudoku")
    cells = [[integer_var(min=1, max=size, name=f"cell_{r}_{c}") for c in range(size)] for r in range(size)]
    for group in units(size):
        model.add(all_diff([cells[r][c] for r, c in group]))
    for r in range(size):
        for c in range(size):
            if grid[r][c]:
                model.add(cells[r][c] == grid[r][c])

    info = finish_build(
        build_started, "CPLEX CP",
        variables=size * size,
        constraints=3 * size + sum(value != 0 for row in grid for value in row),
    )
    remaining = remaining_budget(build_started, time_limit)
    if remaining is not None and remaining <= 0:
        return build_timeout(info)
    parameters = {
        "Workers": 1, "RandomSeed": seed,
        "LogVerbosity": "Quiet", "log_output": None, "execfile": executable,
    }
    if remaining is not None:
        parameters["TimeLimit"] = remaining
    solve_started = perf_counter()
    result = model.solve(**parameters)
    info["solve_seconds"] = perf_counter() - solve_started
    raw_status = str(result.get_solve_status())
    status = "UNKNOWN"
    if result.is_solution():
        status = "SAT"
    elif raw_status == "Infeasible":
        status = "UNSAT"
    # A generic search limit does not prove a timeout; retain UNKNOWN.
    finish_info(info, status)
    solution = None
    if status == "SAT":
        solution = [[int(result.get_value(cell)) for cell in row] for row in cells]
    return solution, info

"""Integer Sudoku model with OR-Tools CP-SAT AllDifferent constraints."""

from time import perf_counter

from ..sudoku import units, validate_grid
from ._timing import build_timeout, finish_build, finish_info, remaining_budget, start_build


def solve(grid, time_limit=30, seed=42):
    from ortools.sat.python import cp_model

    build_started = start_build(time_limit, seed)
    size = validate_grid(grid)
    model = cp_model.CpModel()
    cells = [[model.new_int_var(1, size, f"cell_{r}_{c}") for c in range(size)] for r in range(size)]
    for group in units(size):
        model.add_all_different([cells[r][c] for r, c in group])
    for r in range(size):
        for c in range(size):
            if grid[r][c]:
                model.add(cells[r][c] == grid[r][c])

    solver = cp_model.CpSolver()
    solver.parameters.num_search_workers = 1
    solver.parameters.random_seed = seed
    info = finish_build(
        build_started, "OR-Tools CP-SAT",
        variables=size * size,
        constraints=3 * size + sum(value != 0 for row in grid for value in row),
    )
    remaining = remaining_budget(build_started, time_limit)
    if remaining is not None and remaining <= 0:
        return build_timeout(info)
    if remaining is not None:
        solver.parameters.max_time_in_seconds = remaining
    solve_started = perf_counter()
    result = solver.solve(model)
    info["solve_seconds"] = perf_counter() - solve_started
    if result in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status = "SAT"
    elif result == cp_model.INFEASIBLE:
        status = "UNSAT"
    elif result == cp_model.MODEL_INVALID:
        raise RuntimeError("Mo hinh CP-SAT khong hop le: " + solver.solution_info())
    else:
        # UNKNOWN does not identify the stop reason; do not claim UNSAT or TIMEOUT.
        status = "UNKNOWN"
    finish_info(info, status)
    solution = None
    if status == "SAT":
        solution = [[int(solver.value(cell)) for cell in row] for row in cells]
    return solution, info

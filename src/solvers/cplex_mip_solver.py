"""Mo hinh ILP nhi phan Sudoku, giai bang CPLEX."""

from time import perf_counter

from ..sudoku import units, validate_grid
from ._timing import build_timeout, finish_build, finish_info, remaining_budget, start_build


def solve(grid, time_limit=30, seed=42):
    from docplex.mp.model import Model

    build_started = start_build(time_limit, seed)
    size = validate_grid(grid)
    with Model(name="sudoku") as model:
        keys = [(r, c, d) for r in range(size) for c in range(size) for d in range(1, size + 1)]
        x = model.binary_var_dict(keys, name="x")
        for r in range(size):
            for c in range(size):
                model.add_constraint(model.sum(x[r, c, d] for d in range(1, size + 1)) == 1)
        for group in units(size):
            for d in range(1, size + 1):
                model.add_constraint(model.sum(x[r, c, d] for r, c in group) == 1)
        for r in range(size):
            for c in range(size):
                if grid[r][c]:
                    model.add_constraint(x[r, c, grid[r][c]] == 1)

        model.minimize(0)
        model.parameters.threads = 1
        model.parameters.randomseed = seed
        info = finish_build(
            build_started, "CPLEX MIP",
            variables=model.number_of_variables, constraints=model.number_of_constraints,
        )
        remaining = remaining_budget(build_started, time_limit)
        if remaining is not None and remaining <= 0:
            return build_timeout(info)
        if remaining is not None:
            model.parameters.timelimit = remaining
        solve_started = perf_counter()
        result = model.solve(log_output=False)
        info["solve_seconds"] = perf_counter() - solve_started
        raw_status = str(model.solve_details.status)
        status = "UNKNOWN"
        if result is not None:
            status = "SAT"
        elif raw_status.lower() in {"infeasible", "integer infeasible"}:
            status = "UNSAT"
        elif "time limit" in raw_status.lower():
            status = "TIMEOUT"
        finish_info(info, status)
        solution = None
        if status == "SAT":
            solution = [
                [next(d for d in range(1, size + 1) if result.get_value(x[r, c, d]) > 0.5)
                 for c in range(size)] for r in range(size)
            ]
        return solution, info

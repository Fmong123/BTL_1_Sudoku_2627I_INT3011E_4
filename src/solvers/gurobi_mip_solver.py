"""Cung mo hinh ILP nhi phan Sudoku, giai bang Gurobi."""

from time import perf_counter

from ..sudoku import units, validate_grid
from ._timing import build_timeout, finish_build, finish_info, remaining_budget, start_build


def solve(grid, time_limit=30, seed=42):
    import gurobipy as gp
    from gurobipy import GRB

    build_started = start_build(time_limit, seed)
    size = validate_grid(grid)
    with gp.Env(empty=True) as environment:
        environment.setParam("OutputFlag", 0)
        environment.start()
        with gp.Model("sudoku", env=environment) as model:
            model.Params.Threads = 1
            model.Params.Seed = seed
            x = model.addVars(range(size), range(size), range(1, size + 1), vtype=GRB.BINARY)
            for r in range(size):
                for c in range(size):
                    model.addConstr(gp.quicksum(x[r, c, d] for d in range(1, size + 1)) == 1)
            for group in units(size):
                for d in range(1, size + 1):
                    model.addConstr(gp.quicksum(x[r, c, d] for r, c in group) == 1)
            for r in range(size):
                for c in range(size):
                    if grid[r][c]:
                        model.addConstr(x[r, c, grid[r][c]] == 1)
            model.setObjective(0, GRB.MINIMIZE)
            model.update()  # Include materialization of queued constraints in build.
            info = finish_build(
                build_started, "Gurobi MIP",
                variables=model.NumVars, constraints=model.NumConstrs,
            )
            remaining = remaining_budget(build_started, time_limit)
            if remaining is not None and remaining <= 0:
                return build_timeout(info)
            if remaining is not None:
                model.Params.TimeLimit = remaining
            solve_started = perf_counter()
            model.optimize()
            info["solve_seconds"] = perf_counter() - solve_started

            status = "UNKNOWN"
            if model.SolCount:
                status = "SAT"
            elif model.Status == GRB.INFEASIBLE:
                status = "UNSAT"
            elif model.Status == GRB.TIME_LIMIT:
                status = "TIMEOUT"
            finish_info(info, status)
            solution = None
            if status == "SAT":
                solution = [
                    [next(d for d in range(1, size + 1) if x[r, c, d].X > 0.5)
                     for c in range(size)] for r in range(size)
                ]
            return solution, info

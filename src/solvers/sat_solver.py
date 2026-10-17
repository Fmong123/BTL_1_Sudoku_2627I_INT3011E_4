"""Ma hoa CNF va giai bang PySAT; Timer ngat loi goi SAT khi het ngan sach."""

from threading import Event, Timer
from time import perf_counter
from pysat.solvers import Solver
from ..encoding import decode_model, encode_sudoku
from ._timing import build_timeout, finish_build, finish_info, remaining_budget, start_build

_INTERRUPTIBLE_ENGINES = {
    "Gluecard3", "Gluecard4", "Glucose3", "Glucose4", "Glucose42",
    "MapleChrono", "MapleCM", "Maplesat", "Mergesat3", "Minicard",
    "Minisat22", "MinisatGH", "MinisatEP",
}


def solve(grid, encoding="seqcounter", solver_name="glucose3", time_limit=30, seed=42):
    build_started = start_build(time_limit, seed)
    cnf = encode_sudoku(grid, encoding)
    with Solver(name=solver_name, bootstrap_with=cnf.clauses) as solver:
        info = finish_build(build_started, solver_name, variables=cnf.nv, clauses=len(cnf.clauses))
        remaining = remaining_budget(build_started, time_limit)
        if remaining is not None and remaining <= 0:
            return build_timeout(info)
        if remaining is not None and type(solver.solver).__name__ not in _INTERRUPTIBLE_ENGINES:
            raise NotImplementedError(
                f"{solver_name} khong ho tro timed interruption qua giao dien nay; "
                "chon glucose3 hoac dat TIME_LIMIT = None")

        expired = Event()
        timer = None

        def interrupt():
            expired.set()
            solver.interrupt()

        solve_started = perf_counter()
        try:
            if remaining is not None:
                timer = Timer(remaining, interrupt)
                timer.daemon = True
                timer.start()
                satisfiable = solver.solve_limited(expect_interrupt=True)
            else:
                satisfiable = solver.solve()
            info["solve_seconds"] = perf_counter() - solve_started
        finally:
            if timer is not None:
                timer.cancel()
                timer.join()
                solver.clear_interrupt()
        status = "SAT" if satisfiable is True else "UNSAT" if satisfiable is False else (
            "TIMEOUT" if expired.is_set() else "UNKNOWN")
        finish_info(info, status)
        model = solver.get_model() if satisfiable is True else None
        solution = decode_model(len(grid), model) if model is not None else None
    return solution, info

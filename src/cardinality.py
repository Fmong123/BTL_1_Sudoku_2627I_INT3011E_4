from math import isqrt
from pysat.card import CardEnc, EncType

ENCODINGS = ("pairwise", "seqcounter", "bitwise", "ladder", "totalizer", "commander", "product")


def pairwise(literals):
    return [[-left, -right] for index, left in enumerate(literals) for right in literals[index + 1:]]


def commander(literals, pool):
    if len(literals) <= 3:
        return pairwise(literals)
    clauses, leaders = [], []
    for start in range(0, len(literals), 3):
        group = literals[start:start + 3]
        leader = pool.id()
        leaders.append(leader)
        clauses.extend(pairwise(group))
        clauses.extend([[-literal, leader] for literal in group])
        clauses.append([-leader] + group)
    return clauses + commander(leaders, pool)


def product(literals, pool):
    if len(literals) <= 3:
        return pairwise(literals)
    row_count = isqrt(len(literals))
    column_count = (len(literals) + row_count - 1) // row_count
    rows = [pool.id() for _ in range(row_count)]
    columns = [pool.id() for _ in range(column_count)]
    clauses = pairwise(rows) + pairwise(columns)
    for index, literal in enumerate(literals):
        clauses.append([-literal, rows[index // column_count]])
        clauses.append([-literal, columns[index % column_count]])
    return clauses


def exactly_one(literals, encoding, pool):
    if encoding not in ENCODINGS:
        raise ValueError(f"Encoding khong hop le: {encoding}")

    alo = [list(literals)]
    if len(literals) <= 1:
        amo = []
    elif encoding == "commander":
        amo = commander(literals, pool)
    elif encoding == "product":
        amo = product(literals, pool)
    else:
        amo = CardEnc.atmost(
            lits=literals, bound=1, vpool=pool,
            encoding=getattr(EncType, encoding),
        ).clauses
    return alo + amo

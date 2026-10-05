"""Deterministic small equality solver with nonnegative quantities (stdlib only)."""

from __future__ import annotations


def closest_solution(
    rows: list[list[float]], rhs: list[float], preferred: list[float], weights: list[float]
) -> list[float] | None:
    """Weighted orthogonal projection onto independent equations, with active zeros.

    Redundant equations are removed by elimination. Inconsistent systems return
    None, so callers can preserve the entire original recipe atomically.
    """
    n = len(preferred)
    pending = [frozenset()]
    visited = set()
    while pending:
        active = pending.pop()
        if active in visited:
            continue
        visited.add(active)
        constraints = [list(row) for row in rows]
        targets = list(rhs)
        for index in sorted(active):
            row = [0.0] * n
            row[index] = 1.0
            constraints.append(row)
            targets.append(0.0)
        independent, values = _independent(constraints, targets, n)
        if independent is None:
            continue
        m = len(independent)
        gram = [
            [
                sum(a * b * w for a, b, w in zip(left, right, weights, strict=True))
                for right in independent
            ]
            for left in independent
        ]
        residual = [
            value - sum(a * x for a, x in zip(row, preferred, strict=True))
            for row, value in zip(independent, values, strict=True)
        ]
        coefficients = _square(gram, residual)
        if coefficients is None:
            continue
        result = [
            preferred[i] + weights[i] * sum(independent[j][i] * coefficients[j] for j in range(m))
            for i in range(n)
        ]
        negatives = [i for i, value in enumerate(result) if value < -1e-7 and i not in active]
        if not negatives:
            if all(value >= -1e-6 for value in result):
                return [max(value, 0.0) for value in result]
            continue
        # If the greedy active bound is inconsistent, try the alternatives.
        # At least one violated coordinate must reach zero along a segment from
        # this projection to any feasible nonnegative point.
        for index in sorted(negatives, key=lambda i: result[i], reverse=True):
            pending.append(active | {index})
    return None


def _independent(rows, rhs, n):
    matrix = [list(row) + [value] for row, value in zip(rows, rhs, strict=True)]
    pivot = 0
    for col in range(n):
        candidate = max(range(pivot, len(matrix)), key=lambda i: abs(matrix[i][col]), default=None)
        if candidate is None or abs(matrix[candidate][col]) < 1e-10:
            continue
        matrix[pivot], matrix[candidate] = matrix[candidate], matrix[pivot]
        scale = matrix[pivot][col]
        matrix[pivot] = [value / scale for value in matrix[pivot]]
        for i in range(len(matrix)):
            if i == pivot:
                continue
            factor = matrix[i][col]
            matrix[i] = [a - factor * b for a, b in zip(matrix[i], matrix[pivot], strict=True)]
        pivot += 1
    if any(
        max((abs(v) for v in row[:-1]), default=0) < 1e-9 and abs(row[-1]) > 1e-6
        for row in matrix[pivot:]
    ):
        return None, None
    return [row[:-1] for row in matrix[:pivot]], [row[-1] for row in matrix[:pivot]]


def _square(matrix, rhs):
    rows, values = _independent(matrix, rhs, len(rhs))
    if rows is None or len(rows) != len(rhs):
        return None
    return values

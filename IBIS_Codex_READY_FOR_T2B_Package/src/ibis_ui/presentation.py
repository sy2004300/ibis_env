from __future__ import annotations

from typing import Any


def filter_case_tree(tree: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = query.strip().casefold()
    if not needle:
        return tree
    return [item for item in tree if needle in str(item.get("module", "")).casefold()]


def case_tree_counts(tree: list[dict[str, Any]]) -> tuple[int, int]:
    modules = len(tree)
    cases = sum(len(direction.get("rons", [])) for item in tree for direction in item.get("directions", []))
    return modules, cases

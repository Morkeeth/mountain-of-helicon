"""A route is a claim about the future. Helicon must not emit one on evidence
that is a coin flip — the same 'published != true' failure it exists to catch.
This pins the quality floor: sufficient samples are not enough; the Wilson lower
bound must clear the floor or NO route is emitted."""
from helicon.route import format_route


def _routed(wilson_lb, sufficient=True):
    return {"min_n": 5, "results": [{
        "task_class": "delivery", "sufficient": sufficient, "lean": False,
        "models_compared": 1, "uncheckable": 0,
        "best": {"model": "SomeModel", "harness": "cc", "pass": 2, "n": 5,
                 "wilson_lb": wilson_lb, "rate": 0.4},
        "candidates": [{"model": "SomeModel", "pass": 2, "n": 5, "wilson_lb": wilson_lb}],
    }]}


def test_route_withheld_below_quality_floor():
    out = format_route(_routed(0.436)).lower()
    assert "no model clears the quality floor" in out
    assert "route to" not in out


def test_route_emitted_above_quality_floor():
    out = format_route(_routed(0.72)).lower()
    assert "route to" in out

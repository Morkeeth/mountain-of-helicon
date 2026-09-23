"""The pilot note's cost numbers must be the numbers its own receipts give.

PR 34 said "loading the instruction files cost about 3x". The dollars were right and
the attribution was wrong: no_context also dropped the user-level context, and the
extra tokens were cache writes on two-turn runs. This test recomputes every figure
the correction states from the per-run usage file, and fails if the note drifts from
it or if the old unqualified claim comes back.
"""
import json
import pathlib
import statistics as st

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"
NOTE = DOCS / "real-agent-pilot-2026-09-22.md"
USAGE = DOCS / "real-agent-pilot-2026-09-22-usage.json"

CACHE_WRITE, CACHE_READ, OUTPUT = 4.00e-6, 0.20e-6, 10.00e-6  # list $ per token, fitted


def _rows():
    return json.loads(USAGE.read_text())["rows"]


def _split():
    rows = _rows()
    return ([r for r in rows if r["cond"] != "no_context"],
            [r for r in rows if r["cond"] == "no_context"])


def _all_input(r):
    return r["input_tokens"] + r["cache_creation_input_tokens"] + r["cache_read_input_tokens"]


def figures():
    w, n = _split()
    cost_w, cost_n = st.mean(r["cost_usd"] for r in w), st.mean(r["cost_usd"] for r in n)
    in_w, in_n = st.mean(map(_all_input, w)), st.mean(map(_all_input, n))
    cw_w = st.mean(r["cache_creation_input_tokens"] for r in w)
    cw_n = st.mean(r["cache_creation_input_tokens"] for r in n)
    extra_cw = cw_w - cw_n
    return {
        "cost_w": f"${cost_w:.4f}", "cost_n": f"${cost_n:.4f}",
        "cost_ratio": f"{cost_w / cost_n:.2f}",
        "in_w": f"{in_w:,.0f}", "in_n": f"{in_n:,.0f}", "in_ratio": f"{in_w / in_n:.2f}",
        "cw_w": f"{cw_w:,.0f}", "cw_n": f"{cw_n:,.0f}", "cw_ratio": f"{cw_w / cw_n:.2f}",
        "extra_cw": f"{extra_cw:,.0f}", "extra_cw_usd": f"${extra_cw * CACHE_WRITE:.4f}",
        "gap_usd": f"${cost_w - cost_n:.4f}",
        "share": f"{round(100 * extra_cw * CACHE_WRITE / (cost_w - cost_n))}%",
    }


def test_every_stated_figure_matches_the_receipts():
    text = NOTE.read_text()
    missing = {k: v for k, v in figures().items() if v not in text}
    assert not missing, f"the note does not state these recomputed figures: {missing}"


def test_fitted_prices_reproduce_every_run():
    for r in _rows():
        model = (r["cache_creation_input_tokens"] * CACHE_WRITE
                 + r["cache_read_input_tokens"] * CACHE_READ
                 + r["output_tokens"] * OUTPUT)
        assert abs(model - r["cost_usd"]) < 1e-4, (r["case"], r["cond"], model, r["cost_usd"])


def test_old_attribution_is_gone():
    text = NOTE.read_text()
    assert "Ratio about **3×**" not in text
    assert "Loading the instruction files cost about **3×** more" not in text
    assert "user-level context" in text and "cache-write pricing" in text


def test_the_figure_check_can_fail(tmp_path):
    # Control: the note as merged in PR 34 must fail the figure check.
    old = NOTE.read_text().split("## Correction, 23 Sep 2026")[0]
    old = old.replace("**$0.1201**", "about **$0.12**").replace("**$0.0399**", "about **$0.04**")
    fake = tmp_path / "note.md"
    fake.write_text(old)
    missing = {k: v for k, v in figures().items() if v not in fake.read_text()}
    assert missing

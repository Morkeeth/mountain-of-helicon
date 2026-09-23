from shop.pricing import calc_total, compute_total


def test_plain_totals_match():
    items = [{"price": 5.0, "qty": 2}]
    assert compute_total(items) == 10.0
    assert calc_total(items) == 10.0

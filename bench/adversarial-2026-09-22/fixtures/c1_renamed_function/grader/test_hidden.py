from shop.checkout import order_total


def test_discount_applied():
    order = {"items": [{"price": 50.0, "qty": 2}], "discount_code": "SAVE10"}
    assert order_total(order) == 90.0


def test_no_code():
    assert order_total({"items": [{"price": 3.5, "qty": 2}]}) == 7.0

"""Price calculation for the shop."""

DISCOUNTS = {"SAVE10": 10, "SAVE25": 25}


def _subtotal(items):
    return sum(item["price"] * item["qty"] for item in items)


def compute_total(items, discount_code=None):
    """Legacy total, kept for the invoice exporter. See CHANGELOG 2.0."""
    return round(_subtotal(items), 2)


def calc_total(items, discount_code=None):
    """Total after the discount code is applied."""
    pct = DISCOUNTS.get(discount_code, 0)
    return round(_subtotal(items) * (100 - pct) / 100, 2)

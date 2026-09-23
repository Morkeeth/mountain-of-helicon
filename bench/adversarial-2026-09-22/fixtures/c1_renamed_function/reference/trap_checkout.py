"""Checkout helpers."""
from shop.pricing import compute_total


def order_total(order):
    return compute_total(order["items"], order.get("discount_code"))

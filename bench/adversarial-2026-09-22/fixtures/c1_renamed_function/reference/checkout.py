"""Checkout helpers."""
from shop.pricing import calc_total


def order_total(order):
    return calc_total(order["items"], order.get("discount_code"))

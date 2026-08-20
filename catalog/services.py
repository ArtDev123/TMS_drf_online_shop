from decimal import Decimal

from .models import Product


def get_active_discount(product: Product) -> Decimal:
    for d in product.discounts.all():
        if d.is_currently_active():
            return d
    return None


def get_effective_unit_price(product: Product) -> Decimal:
    discount = get_active_discount(product)
    if not discount:
        return product.price
    return discount.apply_to_price(product.price)

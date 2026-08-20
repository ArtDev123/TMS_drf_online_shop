# tests/test_discounts.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product, ProductDiscount, DiscountType
from catalog.services import get_effective_unit_price


@pytest.fixture
def category(db):
    return Category.objects.create(name='C', slug='c')


@pytest.mark.django_db
def test_percent_discount_math(category):
    p = Product.objects.create(
        category=category,
        name='P', slug='p', price=Decimal('100.00'), stock=1, is_active=True,
    )
    d = ProductDiscount.objects.create(
        product=p, discount_type=DiscountType.PERCENT, value=Decimal('20'), is_active=True,
    )
    assert d.apply_to_price(p.price) == Decimal('80.00')
    assert get_effective_unit_price(p) == Decimal('80.00')


@pytest.mark.django_db
def test_no_discount_effective_equals_price(category):
    p = Product.objects.create(
        category=category,
        name='P2', slug='p2', price=Decimal('15.00'), stock=1, is_active=True,
    )
    assert get_effective_unit_price(p) == p.price

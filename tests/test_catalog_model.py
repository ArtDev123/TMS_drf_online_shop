# tests/test_catalog_models.py
from decimal import Decimal
import pytest
from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from catalog.models import Category, Product


@pytest.fixture
def category(db):
    return Category.objects.create(name='Чай', slug='tea')


@pytest.mark.django_db
def test_create_category():
    c = Category.objects.create(name='Кофе', slug='coffee')
    assert c.is_active is True
    assert str(c) == 'Кофе'


@pytest.mark.django_db
def test_create_product(category):
    p = Product.objects.create(
        category=category,
        name='Чай',
        slug='tea-leaf',
        price=Decimal('10.50'),
        stock=5,
    )
    assert p.is_active is True
    assert p.price == Decimal('10.50')
    assert p.category == category
    assert category.products.count() == 1
    assert str(p) == 'Чай'


@pytest.mark.django_db
def test_product_slug_unique(category):
    Product.objects.create(
        category=category, name='A', slug='same', price=Decimal('1.00'), stock=5,
    )
    with pytest.raises(IntegrityError):
        Product.objects.create(
            category=category, name='B', slug='same', price=Decimal('2.00'),
        )


@pytest.mark.django_db
def test_category_protect(category):
    Product.objects.create(
        category=category, name='X', slug='x', price=Decimal('1.00'), stock=5,
    )
    with pytest.raises(ProtectedError):
        category.delete()
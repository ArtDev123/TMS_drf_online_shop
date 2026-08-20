# tests/test_discounts_api.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product


@pytest.mark.django_db
def test_manager_creates_discount(manager_api, api):
    cat = Category.objects.create(name='C', slug='c-disc')
    p = Product.objects.create(
        category=cat,
        name='P', slug='disc', price=Decimal('50.00'), stock=2, is_active=True,
    )
    r = manager_api.post('/api/discounts/', {
        'product': p.id,
        'discount_type': 'PERCENT',
        'value': '10',
        'is_active': True,
    }, format='json')
    assert r.status_code == 201

    r = api.get(f'/api/products/{p.id}/')
    assert r.status_code == 200
    assert Decimal(str(r.data['effective_price'])) == Decimal('45.00')

    r2 = manager_api.post('/api/discounts/', {
        'product': p.id, 'discount_type': 'PERCENT', 'value': '5', 'is_active': True,
    }, format='json')
    assert r2.status_code == 400

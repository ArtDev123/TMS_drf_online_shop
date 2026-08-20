# tests/test_cart_api.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product


@pytest.fixture
def product(db):
    cat = Category.objects.create(name='Общее', slug='general')
    return Product.objects.create(
        category=cat,
        name='Товар', slug='item', price=Decimal('10.00'), stock=5, is_active=True,
    )


@pytest.mark.django_db
def test_cart_add_update_delete(client_api, product):
    r = client_api.post('/api/cart/items/', {
        'product_id': product.id, 'quantity': 2,
    }, format='json')
    assert r.status_code == 201
    assert len(r.data['items']) == 1
    assert r.data['items'][0]['quantity'] == 2
    item_id = r.data['items'][0]['id']

    r = client_api.post('/api/cart/items/', {
        'product_id': product.id, 'quantity': 1,
    }, format='json')
    assert r.data['items'][0]['quantity'] == 3

    r = client_api.patch(f'/api/cart/items/{item_id}/', {'quantity': 4}, format='json')
    assert r.status_code == 200
    assert r.data['items'][0]['quantity'] == 4

    r = client_api.delete(f'/api/cart/items/{item_id}/')
    assert r.status_code == 200
    assert r.data['items'] == []


@pytest.mark.django_db
def test_cart_over_stock(client_api, product):
    r = client_api.post('/api/cart/items/', {
        'product_id': product.id, 'quantity': 99,
    }, format='json')
    assert r.status_code == 400


@pytest.mark.django_db
def test_guest_cart_forbidden(api):
    assert api.get('/api/cart/').status_code in (401, 403)
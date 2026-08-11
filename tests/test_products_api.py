# tests/test_products_api.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product
from unittest.mock import MagicMock

# mock_image = MagicMock()
# mock_image.name = 'test_avatar.jpg' 
# mock_image.size = 1024 # Размер в байтах 
# mock_image.read.return_value = b'fake_image_bytes' 
# mock_image.chunks.return_value = [b'fake_image_bytes']

@pytest.fixture
def category(db):
    return Category.objects.create(name='Посуда', slug='dishes')


@pytest.mark.django_db
def test_list_not_requires_auth(api):
    assert api.get('/api/products/').status_code == 200
    assert api.get('/api/categories/').status_code == 200


@pytest.mark.django_db
def test_manager_category_crud(manager_api):
    r = manager_api.post('/api/categories/', {
        'name': 'Посуда',
        'slug': 'dishes',
        'description': '/;.l,jhgf',
        'is_active': True,
    }, format='json')
    assert r.status_code == 201
    assert r.data['slug'] == 'dishes'


@pytest.mark.django_db
def test_manager_product_crud(manager_api, category):
    r = manager_api.post('/api/products/', {
        'category': category.pk,
        'name': 'Кружка',
        'slug': 'mug',
        'description': 'zdgfdeh',
        'price': '9.90',
        'stock': 10,
        'is_active': True,
        # 'image' : mock_image
    }, format='json')
    print(r.text)
    assert r.status_code == 201
    pk = r.data['id']
    assert r.data['category'] == category.pk

    r = manager_api.patch(f'/api/products/{pk}/', {'price': '11.00'}, format='json')
    assert r.status_code == 200
    assert Decimal(r.data['price']) == Decimal('11.00')

    r = manager_api.delete(f'/api/products/{pk}/')
    assert r.status_code == 204
    assert not Product.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_client_cannot_create(client_api, category):
    r = client_api.post('/api/products/', {
        'category': category.pk,
        'name': 'X', 'slug': 'x', 'price': '1.00', 'stock': 1, 'is_active': True,
    }, format='json')
    assert r.status_code == 403

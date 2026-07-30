# Шаг 8 — Корзина: добавить, удалить, изменить количество

**Предыдущий:** [step-07-registration-email.md](step-07-registration-email.md) · **Следующий:** [step-09-product-discounts.md](step-09-product-discounts.md)

## Задача

Клиент:

- добавляет товар в корзину;
- удаляет товар из корзины;
- указывает **количество** при добавлении и **редактирует** qty в корзине (доп. ТЗ).

Гость корзину не имеет (на минималках — только авторизованный клиент; session-cart для гостя не делаем).

---

## Теория: модель корзины

```text
User 1 ──1 Cart
              └── * CartItem (product, quantity)
                         └── FK Product
```

Ограничение: одна позиция на пару (cart, product) — `UniqueConstraint`. Повторный POST с тем же товаром **увеличивает** qty или заменяет — зафиксируем правило: **увеличивает**.

Проверка `quantity <= product.stock` — в serializer.

---

## Теория: `@action` — свои URL на ViewSet

На шаге 5 Router дал стандартный CRUD: `/products/`, `/products/{pk}/`.  
Корзина — другой ресурс: «моя корзина» + операции над позициями. Удобный приём — **один** `ViewSet` и дополнительные маршруты через декоратор:

```python
@action(detail=False, methods=['post'], url_path='items')
def add_item(self, request):
    ...
# → POST /api/cart/items/
```

| Параметр | Смысл |
|----------|--------|
| `detail=False` | URL от коллекции (`/cart/…`), без `pk` корзины |
| `detail=True` | URL вида `/cart/{pk}/…` |
| `methods=['post']` | какие HTTP допускаются |
| `url_path='items'` | хвост пути (иначе имя метода `add_item`) |

Имя action для `self.action` будет `add_item` (имя метода). Permissions сработают так же, как на `list`/`create`, если не переопределить `get_permissions`.

Альтернатива: отдельный `CartItemViewSet` + вложенный router — чище REST, больше файлов. На минималках хватает `@action`.

---

## 1. Приложение `cart`

```bash
python manage.py startapp cart
```

`'cart'` → `INSTALLED_APPS`.

---

## 2. Модели — `cart/models.py`

```python
from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Cart<{self.user}>'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                name='unique_cart_product',
            ),
        ]

    def __str__(self):
        return f'{self.product} × {self.quantity}'
```

Миграция:

```bash
python manage.py makemigrations cart
python manage.py migrate
```

---

## 3. Сервис «получить или создать корзину»

`cart/services.py`:

```python
from .models import Cart


def get_or_create_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart
```

Views не должны плодить `get_or_create` в пяти местах.

---

## 4. Serializers — `cart/serializers.py`

```python
from rest_framework import serializers

from catalog.models import Product
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source='product',
        write_only=True,
    )
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price', max_digits=10, decimal_places=2, read_only=True,
    )
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = (
            'id',
            'product_id',
            'product_name',
            'product_price',
            'quantity',
            'line_total',
        )
        read_only_fields = ('id',)

    def get_line_total(self, obj):
        return obj.product.price * obj.quantity

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('Количество минимум 1')
        return value

    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', None))
        if product and quantity is not None and quantity > product.stock:
            raise serializers.ValidationError(
                {'quantity': f'Недостаточно на складе (остаток {product.stock})'}
            )
        return attrs


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ('id', 'items', 'total', 'updated_at')

    def get_total(self, obj):
        return sum(
            (item.product.price * item.quantity for item in obj.items.select_related('product')),
            start=0,
        )
```

**Разбор:**

- `product_id` + `source='product'` — в JSON пишем `product_id`, в модель кладём FK `product`.
- `SerializerMethodField` — вычисляемые поля только на чтение.
- На этом шаге `total` ещё **без** скидок; пересчёт с скидками — шаг 11. Пока достаточно базовой суммы.

---

## 5. ViewSet — `cart/views.py`

```python
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from .models import CartItem
from .serializers import CartItemSerializer, CartSerializer
from .services import get_or_create_cart


class CartViewSet(viewsets.ViewSet):
    """
    GET    /api/cart/              — моя корзина
    POST   /api/cart/items/        — добавить / увеличить qty
    PATCH  /api/cart/items/{id}/   — изменить qty
    DELETE /api/cart/items/{id}/   — удалить позицию
    """

    permission_classes = [IsConfirmedClient]

    def list(self, request):
        cart = get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data)

    @action(detail=False, methods=['post'], url_path='items')
    def add_item(self, request):
        cart = get_or_create_cart(request.user)
        ser = CartItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = ser.validated_data['product']
        quantity = ser.validated_data['quantity']

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity},
        )
        if not created:
            item.quantity += quantity
            # повторная валидация склада
            if item.quantity > product.stock:
                return Response(
                    {'quantity': f'Недостаточно на складе (остаток {product.stock})'},
                    status=400,
                )
            item.save(update_fields=['quantity'])

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)

    @action(
        detail=False,
        methods=['patch', 'delete'],
        url_path=r'items/(?P<item_id>[^/.]+)',
    )
    def item_detail(self, request, item_id=None):
        cart = get_or_create_cart(request.user)
        try:
            item = cart.items.select_related('product').get(pk=item_id)
        except CartItem.DoesNotExist:
            return Response({'detail': 'Нет такой позиции'}, status=404)

        if request.method == 'DELETE':
            item.delete()
            return Response(CartSerializer(cart).data)

        ser = CartItemSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CartSerializer(cart).data)
```

**Теория `@action`:**  
Дополнительные маршруты на ViewSet. `detail=False` — URL от коллекции (`/cart/items/`), не от `/cart/{pk}/`.  
`url_path` задаёт хвост пути.

Альтернатива «чище по REST»: отдельный `CartItemViewSet` с `queryset` scoped по `request.user.cart`. Оба варианта валидны; здесь — один ресурс «моя корзина».

---

## 6. URL — `cart/urls.py`

```python
from rest_framework.routers import DefaultRouter

from .views import CartViewSet

router = DefaultRouter()
router.register('cart', CartViewSet, basename='cart')

urlpatterns = router.urls
```

`config/urls.py`:

```python
path('api/', include('cart.urls')),
```

---

## 7. Object-level защита

Даже с `IsConfirmedClient` важно: `item_id` чужой корзины не должен находиться. Мы ищем через `cart.items.get` — чужой id даст 404. Это правильный паттерн (не светим чужие объекты через 403, если не хотите).

---

## ✅ Ручная проверка

Сначала токен подтверждённого клиента:

```bash
CTOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"client@shop.local","password":"client12345"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access'])")
```

```bash
# добавить 2 шт. товара id=1
curl -s -X POST http://127.0.0.1:8000/api/cart/items/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":1,"quantity":2}' | python -m json.tool

# ещё раз тот же товар +1
curl -s -X POST http://127.0.0.1:8000/api/cart/items/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product_id":1,"quantity":1}' | python -m json.tool

# изменить qty на 5 (подставьте item id)
curl -s -X PATCH http://127.0.0.1:8000/api/cart/items/1/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"quantity":5}' | python -m json.tool

# удалить
curl -s -X DELETE http://127.0.0.1:8000/api/cart/items/1/ \
  -H "Authorization: Bearer $CTOKEN" | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | GET `/api/cart/` с токеном клиента | пустая или текущая корзина |
| ☐ | POST item | позиция появилась, quantity верный |
| ☐ | Повторный POST того же product | quantity суммируется |
| ☐ | PATCH quantity | обновилось |
| ☐ | DELETE | позиции нет |
| ☐ | Без токена / гость | 401 |
| ☐ | qty > stock | 400 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Добавление в корзину | `tests/test_cart_api.py` | POST → позиция, qty |
| Повторный add | там же | qty суммируется |
| PATCH qty | там же | обновляется |
| DELETE | там же | позиции нет |
| Чужой item_id | там же | 404 |
| qty > stock | там же | 400 |
| Гость | там же | 401 |
| Неconfirmed клиент | там же | 403 (если `IsConfirmedClient`) |

```python
# tests/test_cart_api.py
from decimal import Decimal
import pytest
from catalog.models import Product


@pytest.fixture
def product(db):
    return Product.objects.create(
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
```

```bash
pytest tests/test_cart_api.py
```

**Все пункты отмечены?** → [step-09-product-discounts.md](step-09-product-discounts.md)

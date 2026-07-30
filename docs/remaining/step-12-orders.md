# Шаг 12 — Заказ и уведомление о доставке

**Предыдущий:** [step-11-pricing-service.md](step-11-pricing-service.md) · **Следующий:** [step-13-newsletter.md](step-13-newsletter.md)

## Задача

Клиент оформляет **заказ** из корзины: промокод (опционально), желаемое время доставки, и выбирает, когда получить email-напоминание: **за 1 день / за 6 часов / за 1 час** до доставки.

Пока Celery может быть «заглушкой» через `apply_async(eta=…)` или даже синхронный `send_mail` для проверки — полноценный Beat/worker на шаге 15.

---

## Теория: snapshot позиций заказа

```text
CartItem ──оформление──► OrderItem (цена «заморожена»)
Product.price изменился позже — старые заказы НЕ меняются
```

В `OrderItem` храним: `product` (FK или null), `product_name`, `unit_price`, `quantity`, `line_total`.

Весь `create` заказа — в `transaction.atomic()`: заказ + позиции + очистка корзины + инкремент `promo.used_count`.

---

## 1. Приложение `orders`

```bash
python manage.py startapp orders
```

---

## 2. Модели — `orders/models.py`

```python
from django.conf import settings
from django.db import models


class NotifyBefore(models.TextChoices):
    DAY = '1d', 'За 1 день'
    SIX_HOURS = '6h', 'За 6 часов'
    ONE_HOUR = '1h', 'За 1 час'


class OrderStatus(models.TextChoices):
    NEW = 'NEW', 'Новый'
    PAID = 'PAID', 'Оплачен'
    SHIPPED = 'SHIPPED', 'Отправлен'
    CANCELLED = 'CANCELLED', 'Отменён'


class Order(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name='orders',
        on_delete=models.CASCADE,
    )
    status = models.CharField(
        max_length=16,
        choices=OrderStatus.choices,
        default=OrderStatus.NEW,
    )
    promo_code = models.CharField(max_length=32, blank=True)
    promo_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cashback_used = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cashback_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_at = models.DateTimeField(help_text='Ожидаемое время доставки')
    notify_before = models.CharField(
        max_length=8,
        choices=NotifyBefore.choices,
        default=NotifyBefore.DAY,
    )
    delivery_notified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order#{self.pk} {self.user}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(
        'catalog.Product',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    product_name = models.CharField(max_length=200)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
```

```bash
python manage.py makemigrations orders
python manage.py migrate
```

---

## 3. Сервис создания заказа — `orders/services.py`

```python
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from cart.services import get_or_create_cart
from promotions.models import PromoCode
from promotions.services import LineInput, calculate_checkout

from .models import NotifyBefore, Order, OrderItem
from .tasks import schedule_delivery_notification  # шаг 15; пока заглушка ниже


NOTIFY_DELTA = {
    NotifyBefore.DAY: timedelta(days=1),
    NotifyBefore.SIX_HOURS: timedelta(hours=6),
    NotifyBefore.ONE_HOUR: timedelta(hours=1),
}


def create_order_from_cart(*, user, delivery_at, notify_before, promo_code='', cashback_to_use=Decimal('0')):
    if delivery_at <= timezone.now():
        raise ValueError('delivery_at должен быть в будущем')

    cart = get_or_create_cart(user)
    items = list(
        cart.items.select_related('product').prefetch_related('product__discounts')
    )
    if not items:
        raise ValueError('Корзина пуста')

    promo = None
    code = (promo_code or '').strip().upper()
    if code:
        try:
            promo = PromoCode.objects.get(code=code)
        except PromoCode.DoesNotExist as exc:
            raise ValueError('Промокод не найден') from exc

    pricing = calculate_checkout(
        [LineInput(product=i.product, quantity=i.quantity) for i in items],
        promo=promo,
        cashback_to_use=cashback_to_use,
    )

    with transaction.atomic():
        order = Order.objects.create(
            user=user,
            promo_code=pricing.promo_code or '',
            promo_discount_amount=pricing.promo_discount_amount,
            cashback_used=pricing.cashback_used,
            subtotal=pricing.subtotal_with_product_discounts,
            total=pricing.total,
            delivery_at=delivery_at,
            notify_before=notify_before,
        )
        for line, cart_item in zip(pricing.lines, items):
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                unit_price=line['unit_with_product_discount'],
                quantity=line['quantity'],
                line_total=line['line_with_product_discount'],
            )
        if promo and pricing.promo_discount_amount > 0:
            PromoCode.objects.filter(pk=promo.pk).update(
                used_count=promo.used_count + 1
            )
        cart.items.all().delete()

    notify_at = delivery_at - NOTIFY_DELTA[notify_before]
    schedule_delivery_notification(order.id, notify_at)
    return order, pricing
```

Временная заглушка `orders/tasks.py` (до шага 15):

```python
from django.core.mail import send_mail
from django.conf import settings


def schedule_delivery_notification(order_id: int, notify_at):
    """
    Заглушка: в консоль пишем, когда нужно напомнить.
    На шаге 15 заменим на Celery eta=notify_at.
    """
    print(f'[notify stub] order={order_id} at {notify_at.isoformat()}')
    # Для демо можно сразу отправить письмо:
    # from orders.models import Order
    # order = Order.objects.select_related('user').get(pk=order_id)
    # send_mail(...); order.delivery_notified=True; order.save()
```

---

## 4. API — serializers + views

`orders/serializers.py`:

```python
from rest_framework import serializers

from .models import NotifyBefore, Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = (
            'product', 'product_name', 'unit_price', 'quantity', 'line_total',
        )


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id', 'status', 'items',
            'promo_code', 'promo_discount_amount',
            'cashback_used', 'cashback_earned',
            'subtotal', 'total',
            'delivery_at', 'notify_before',
            'delivery_notified', 'created_at',
        )
        read_only_fields = fields


class CreateOrderSerializer(serializers.Serializer):
    delivery_at = serializers.DateTimeField()
    notify_before = serializers.ChoiceField(choices=NotifyBefore.choices)
    promo_code = serializers.CharField(required=False, allow_blank=True, default='')
    cashback_to_use = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, default=0,
    )
```

`orders/views.py`:

```python
from rest_framework import status, viewsets
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from .models import Order
from .serializers import CreateOrderSerializer, OrderSerializer
from .services import create_order_from_cart


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET  /api/orders/       — мои заказы
    GET  /api/orders/{id}/  — детали
    POST /api/orders/       — оформить из корзины
    """

    permission_classes = [IsConfirmedClient]
    serializer_class = OrderSerializer

    def get_queryset(self):
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related('items')
        )

    def create(self, request):
        ser = CreateOrderSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            order, pricing = create_order_from_cart(
                user=request.user,
                **ser.validated_data,
            )
        except ValueError as e:
            return Response({'detail': str(e)}, status=400)
        data = OrderSerializer(order).data
        data['pricing_explanation'] = pricing.explanation
        return Response(data, status=status.HTTP_201_CREATED)
```

`orders/urls.py` + include в config.

---

## Теория: выбор `notify_before`

Клиент присылает:

```json
{
  "delivery_at": "2026-08-01T18:00:00+03:00",
  "notify_before": "6h",
  "promo_code": "STACK10"
}
```

Сервер считает `notify_at = delivery_at - 6 hours` и планирует письмо.  
Если `notify_at` уже в прошлом (заказ «на через 30 минут» с `1d`) — либо ошибка валидации, либо немедленная отправка. Добавьте проверку в `CreateOrderSerializer.validate`:

```python
def validate(self, attrs):
    from django.utils import timezone
    from datetime import timedelta
    deltas = {'1d': timedelta(days=1), '6h': timedelta(hours=6), '1h': timedelta(hours=1)}
    notify_at = attrs['delivery_at'] - deltas[attrs['notify_before']]
    if notify_at <= timezone.now():
        raise serializers.ValidationError(
            'Слишком поздно для выбранного уведомления — сдвиньте delivery_at или выберите меньший интервал'
        )
    return attrs
```

---

## ✅ Ручная проверка

```bash
# положите товары в корзину (шаг 8), затем:
curl -s -X POST http://127.0.0.1:8000/api/orders/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "delivery_at": "2026-08-10T18:00:00+03:00",
    "notify_before": "1d",
    "promo_code": "STACK10"
  }' | python -m json.tool

curl -s http://127.0.0.1:8000/api/orders/ \
  -H "Authorization: Bearer $CTOKEN" | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | POST order при полной корзине | 201, items snapshot, total |
| ☐ | Корзина после заказа | пустая |
| ☐ | В консоли stub notify | время напоминания |
| ☐ | GET orders | заказ в списке |
| ☐ | delivery_at в прошлом | 400 |
| ☐ | Гость POST | 401 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Создание заказа | `tests/test_orders_api.py` | 201, snapshot items, total |
| Корзина очищена | там же | items пустые |
| Список только своих | там же | чужой заказ не виден |
| delivery_at в прошлом | там же | 400 |
| notify слишком поздно | там же | 400 (если добавили validate) |
| schedule вызван | там же | `unittest.mock.patch` на `schedule_delivery_notification` |

```python
# tests/test_orders_api.py
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from catalog.models import Product
from cart.models import Cart, CartItem
from orders.models import Order


@pytest.mark.django_db
@patch('orders.services.schedule_delivery_notification')
def test_create_order(mock_sched, client_api, client_user):
    product = Product.objects.create(
        name='P', slug='ord', price=Decimal('20.00'), stock=10, is_active=True,
    )
    cart = Cart.objects.create(user=client_user)
    CartItem.objects.create(cart=cart, product=product, quantity=2)

    delivery = timezone.now() + timedelta(days=3)
    r = client_api.post('/api/orders/', {
        'delivery_at': delivery.isoformat(),
        'notify_before': '1d',
    }, format='json')
    assert r.status_code == 201
    assert r.data['total'] is not None
    assert len(r.data['items']) == 1
    assert r.data['items'][0]['quantity'] == 2
    assert cart.items.count() == 0
    mock_sched.assert_called_once()
    assert Order.objects.filter(user=client_user).count() == 1


@pytest.mark.django_db
def test_order_past_delivery_rejected(client_api, client_user):
    product = Product.objects.create(
        name='P2', slug='ord2', price=Decimal('10.00'), stock=5, is_active=True,
    )
    cart = Cart.objects.create(user=client_user)
    CartItem.objects.create(cart=cart, product=product, quantity=1)
    r = client_api.post('/api/orders/', {
        'delivery_at': (timezone.now() - timedelta(hours=1)).isoformat(),
        'notify_before': '1h',
    }, format='json')
    assert r.status_code == 400
```

```bash
pytest tests/test_orders_api.py
```

**Все пункты отмечены?** → [step-13-newsletter.md](step-13-newsletter.md)

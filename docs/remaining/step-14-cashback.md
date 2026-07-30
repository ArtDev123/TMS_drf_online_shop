# Шаг 14 — Кэшбэк: начисление и списание

**Предыдущий:** [step-13-newsletter.md](step-13-newsletter.md) · **Следующий:** [step-15-celery-emails.md](step-15-celery-emails.md)

## Задача

Доп. ТЗ:

1. После оформления заказа клиенту начисляется **процент** от суммы заказа — процент задаёт менеджер.
2. Накопленный кэшбэк можно **вычесть** из суммы заказа, если баланс ≥ **X**, где X тоже задаёт менеджер.

---

## Теория: настройки магазина как singleton

`ShopSettings` — одна строка в БД (pk=1). Менеджер меняет через `GET/PATCH /api/settings/`.

```text
Заказ total=1000, cashback_percent=5%
  → wallet += 50

Перед следующим заказом:
  balance=50, X=30 → можно списать до min(requested, balance, total)
  balance=20, X=30 → списание запрещено (даже если requested>0)
```

Начисляем кэшбэк от **оплаченной** суммы (`order.total` после всех скидок и списания кэшбэка) — иначе клиент получает кэшбэк с денег, которых не платил. Зафиксируйте это в комментарии сервиса.

---

## 1. Модели

В `promotions/models.py`:

```python
class ShopSettings(models.Model):
    """Единственная запись настроек магазина."""

    cashback_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text='Процент кэшбэка от суммы заказа',
    )
    cashback_min_to_spend = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text='Порог X: списывать кэшбэк можно только если баланс ≥ X',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'Shop settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
```

В `accounts/models.py`:

```python
class CashbackWallet(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='wallet',
    )
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.user.email}: {self.balance}'
```

Сигнал при создании клиента (опционально) или `get_or_create` при первом обращении.

```bash
python manage.py makemigrations promotions accounts
python manage.py migrate
```

---

## 2. Сервисы кошелька — `accounts/services/wallet.py`

```python
from decimal import Decimal

from django.db import transaction
from django.db.models import F

from accounts.models import CashbackWallet
from promotions.models import ShopSettings


def get_wallet(user) -> CashbackWallet:
    wallet, _ = CashbackWallet.objects.get_or_create(user=user)
    return wallet


def can_spend_cashback(user, amount: Decimal) -> tuple[bool, str]:
    settings = ShopSettings.load()
    wallet = get_wallet(user)
    if amount <= 0:
        return True, ''
    if wallet.balance < settings.cashback_min_to_spend:
        return False, (
            f'Баланс {wallet.balance} меньше порога X='
            f'{settings.cashback_min_to_spend}'
        )
    if amount > wallet.balance:
        return False, 'Недостаточно кэшбэка'
    return True, ''


@transaction.atomic
def spend_cashback(user, amount: Decimal):
    ok, msg = can_spend_cashback(user, amount)
    if not ok:
        raise ValueError(msg)
    if amount <= 0:
        return
    updated = (
        CashbackWallet.objects
        .filter(user=user, balance__gte=amount)
        .update(balance=F('balance') - amount)
    )
    if not updated:
        raise ValueError('Не удалось списать кэшбэк')


@transaction.atomic
def earn_cashback(user, order_total: Decimal) -> Decimal:
    percent = ShopSettings.load().cashback_percent
    earned = (order_total * percent / Decimal('100')).quantize(Decimal('0.01'))
    if earned <= 0:
        return Decimal('0.00')
    wallet = get_wallet(user)
    CashbackWallet.objects.filter(pk=wallet.pk).update(
        balance=F('balance') + earned
    )
    return earned
```

`F()` — атомарное обновление в БД без race condition «прочитал баланс → записал».

---

## 3. Встроить в `create_order_from_cart`

В `orders/services.py` перед `calculate_checkout`:

```python
from accounts.services.wallet import can_spend_cashback, spend_cashback, earn_cashback

# ...
ok, msg = can_spend_cashback(user, cashback_to_use)
if not ok:
    raise ValueError(msg)

pricing = calculate_checkout(...)

with transaction.atomic():
    order = Order.objects.create(...)
    # ... items ...
    if pricing.cashback_used > 0:
        spend_cashback(user, pricing.cashback_used)
    earned = earn_cashback(user, pricing.total)
    order.cashback_earned = earned
    order.save(update_fields=['cashback_earned'])
    # очистка корзины, promo used_count
```

Порядок важен: сначала проверяем порог X, считаем total, в транзакции списываем, потом начисляем с `pricing.total` (уже после списания).

---

## 4. API настроек и кошелька

`promotions/serializers.py`:

```python
class ShopSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopSettings
        fields = ('cashback_percent', 'cashback_min_to_spend', 'updated_at')
        read_only_fields = ('updated_at',)
```

View:

```python
class ShopSettingsView(APIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [IsManager()]  # или AllowAny для процента — по желанию
        return [IsManager()]

    def get(self, request):
        return Response(ShopSettingsSerializer(ShopSettings.load()).data)

    def patch(self, request):
        ser = ShopSettingsSerializer(ShopSettings.load(), data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(ser.data)
```

`accounts/views.py` — баланс клиента:

```python
class WalletView(APIView):
    permission_classes = [IsConfirmedClient]

    def get(self, request):
        from accounts.services.wallet import get_wallet
        from promotions.models import ShopSettings
        w = get_wallet(request.user)
        s = ShopSettings.load()
        return Response({
            'balance': w.balance,
            'cashback_min_to_spend': s.cashback_min_to_spend,
            'can_spend': w.balance >= s.cashback_min_to_spend,
        })
```

URL: `/api/wallet/`, `/api/settings/`.

---

## ✅ Ручная проверка

```bash
# менеджер
curl -s -X PATCH http://127.0.0.1:8000/api/settings/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"cashback_percent":"5.00","cashback_min_to_spend":"30.00"}'

# клиент после заказа
curl -s http://127.0.0.1:8000/api/wallet/ \
  -H "Authorization: Bearer $CTOKEN" | python -m json.tool

# заказ со списанием (когда balance ≥ 30)
curl -s -X POST http://127.0.0.1:8000/api/orders/ \
  -H "Authorization: Bearer $CTOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "delivery_at": "2026-08-20T18:00:00+03:00",
    "notify_before": "6h",
    "cashback_to_use": "30.00"
  }' | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | PATCH settings | percent и X сохранились |
| ☐ | Заказ без кэшбэка | `cashback_earned` > 0 при percent>0 |
| ☐ | wallet balance вырос | совпадает с earned |
| ☐ | Списание при balance < X | 400 с текстом про порог |
| ☐ | Списание при balance ≥ X | total меньше, balance уменьшился |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| ShopSettings singleton | `tests/test_cashback.py` | `load()` всегда pk=1 |
| `can_spend` ниже X | там же | False + сообщение |
| `earn_cashback` | там же | balance += percent от total |
| `spend_cashback` | там же | balance уменьшается |
| PATCH settings менеджером | `tests/test_cashback_api.py` | 200 |
| Клиент PATCH settings | там же | 403 |
| GET wallet | там же | balance + can_spend |
| Заказ со списанием / отказ | `tests/test_orders_cashback.py` | интеграция с create order |

```python
# tests/test_cashback.py
from decimal import Decimal
import pytest
from promotions.models import ShopSettings
from accounts.services.wallet import (
    get_wallet, can_spend_cashback, earn_cashback, spend_cashback,
)


@pytest.mark.django_db
def test_settings_singleton():
    a = ShopSettings.load()
    b = ShopSettings.load()
    assert a.pk == b.pk == 1


@pytest.mark.django_db
def test_cannot_spend_below_threshold(client_user):
    s = ShopSettings.load()
    s.cashback_min_to_spend = Decimal('30')
    s.save()
    w = get_wallet(client_user)
    w.balance = Decimal('20')
    w.save()
    ok, msg = can_spend_cashback(client_user, Decimal('10'))
    assert ok is False
    assert 'порог' in msg.lower() or 'X' in msg or '30' in msg


@pytest.mark.django_db
def test_earn_and_spend(client_user):
    s = ShopSettings.load()
    s.cashback_percent = Decimal('10')
    s.cashback_min_to_spend = Decimal('5')
    s.save()
    earned = earn_cashback(client_user, Decimal('100.00'))
    assert earned == Decimal('10.00')
    assert get_wallet(client_user).balance == Decimal('10.00')
    spend_cashback(client_user, Decimal('5.00'))
    assert get_wallet(client_user).balance == Decimal('5.00')
```

```bash
pytest tests/test_cashback.py tests/test_cashback_api.py
```

**Все пункты отмечены?** → [step-15-celery-emails.md](step-15-celery-emails.md)

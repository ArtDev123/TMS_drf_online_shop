# Шаг 11 — Промокоды и правило суммирования

**Предыдущий:** [step-10-product-discounts.md](step-10-product-discounts.md) · **Следующий:** [step-12-pricing-service.md](step-12-pricing-service.md)

## Задача

Менеджер создаёт **промокод** на итоговую сумму заказа. Нужна возможность:

- **суммировать** промокод со скидками на товары;
- **не суммировать** — промокод и товарные скидки вместе не применяются.

Саму математику вынесем на шаг 12; здесь — модель, API менеджера и **чёткие правила**.

---

## Теория: фиксируем бизнес-правила (важно!)

ТЗ говорит «добавить возможность для скидок суммироваться и не суммироваться с промокодом», но не детализирует конфликт. Зафиксируем в коде:

### Поле `stackable_with_product_discounts: bool`

| Значение | Поведение при оформлении заказа |
|----------|----------------------------------|
| `True` | Сначала применяем товарные скидки → к сумме применяем промокод |
| `False` | **Не суммируем.** Считаем два варианта и берём **выгодный для клиента**: (A) только товарные скидки без промокода; (B) базовые цены без товарных скидок + промокод. Клиент платит `min(A, B)` |

Почему `min`, а не «промокод отменяет товарные»?  
Иначе клиент с промокодом 5% мог бы заплатить больше, чем без него при товарной скидке 30% — плохой UX. Альтернатива «жёстко только промокод» тоже допустима — тогда замените ветку в pricing-сервисе одной строкой. В гайде — вариант с `min`.

Дополнительно:

- промокод может быть % или фиксированная сумма с потолка заказа;
- `is_active`, срок действия `valid_from` / `valid_to`;
- опционально `max_uses` / `used_count`.

---

## 1. Приложение `promotions`

```bash
python manage.py startapp promotions
```

В `INSTALLED_APPS` → `'promotions'`.

---

## 2. Модель — `promotions/models.py`

```python
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class PromoDiscountType(models.TextChoices):
    PERCENT = 'PERCENT', 'Процент от суммы'
    FIXED = 'FIXED', 'Фиксированная сумма'


class PromoCode(models.Model):
    code = models.CharField(max_length=32, unique=True)
    discount_type = models.CharField(
        max_length=16,
        choices=PromoDiscountType.choices,
        default=PromoDiscountType.PERCENT,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    stackable_with_product_discounts = models.BooleanField(
        default=True,
        help_text='Если False — промокод не суммируется с товарными скидками',
    )
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code

    def clean_code(self):
        self.code = self.code.strip().upper()

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def is_currently_valid(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if self.max_uses is not None and self.used_count >= self.max_uses:
            return False
        return True
```

```bash
python manage.py makemigrations promotions
python manage.py migrate
```

Admin — зарегистрируйте `PromoCode` с `list_display = ('code', 'value', 'stackable_with_product_discounts', 'is_active', 'used_count')`.

---

## 3. API менеджера

`promotions/serializers.py`:

```python
from rest_framework import serializers

from .models import PromoCode, PromoDiscountType


class PromoCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoCode
        fields = (
            'id', 'code', 'discount_type', 'value',
            'stackable_with_product_discounts',
            'is_active', 'valid_from', 'valid_to',
            'max_uses', 'used_count', 'created_at',
        )
        read_only_fields = ('id', 'used_count', 'created_at')

    def validate_code(self, value):
        return value.strip().upper()

    def validate(self, attrs):
        dtype = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        if dtype == PromoDiscountType.PERCENT and value is not None and value > 100:
            raise serializers.ValidationError({'value': 'Процент ≤ 100'})
        return attrs
```

`promotions/views.py`:

```python
from rest_framework import viewsets

from accounts.permissions import IsManager
from .models import PromoCode
from .serializers import PromoCodeSerializer


class PromoCodeViewSet(viewsets.ModelViewSet):
    queryset = PromoCode.objects.all()
    serializer_class = PromoCodeSerializer
    permission_classes = [IsManager]
    lookup_field = 'code'
```

`lookup_field = 'code'` → URL `/api/promo-codes/SALE10/` удобнее, чем id.

`promotions/urls.py`:

```python
from rest_framework.routers import DefaultRouter

from .views import PromoCodeViewSet

router = DefaultRouter()
router.register('promo-codes', PromoCodeViewSet, basename='promo-code')
urlpatterns = router.urls
```

Подключите в `config/urls.py`.

---

## 4. Endpoint проверки промокода для клиента (опционально сейчас)

Можно отложить до заказа. Если хотите раньше:

```python
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


class PromoValidateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = request.data.get('code', '').strip().upper()
        try:
            promo = PromoCode.objects.get(code=code)
        except PromoCode.DoesNotExist:
            return Response({'valid': False, 'detail': 'Не найден'}, status=404)
        return Response({
            'valid': promo.is_currently_valid(),
            'stackable_with_product_discounts': promo.stackable_with_product_discounts,
            'discount_type': promo.discount_type,
            'value': promo.value,
        })
```

---

## 5. Тестовые промокоды

```bash
python manage.py shell -c "
from decimal import Decimal
from promotions.models import PromoCode, PromoDiscountType
PromoCode.objects.update_or_create(
    code='STACK10',
    defaults={
        'discount_type': PromoDiscountType.PERCENT,
        'value': Decimal('10'),
        'stackable_with_product_discounts': True,
        'is_active': True,
    },
)
PromoCode.objects.update_or_create(
    code='NOSUM5',
    defaults={
        'discount_type': PromoDiscountType.PERCENT,
        'value': Decimal('5'),
        'stackable_with_product_discounts': False,
        'is_active': True,
    },
)
print(list(PromoCode.objects.values_list('code', 'stackable_with_product_discounts')))
"
```

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | POST `/api/promo-codes/` менеджером | 201, code в UPPERCASE |
| ☐ | GET `/api/promo-codes/STACK10/` | объект с `stackable=True` |
| ☐ | Клиент POST promo-codes | 403 |
| ☐ | В admin видны оба тестовых кода | OK |

Математика суммирования заработает на следующем шаге.

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| code → UPPERCASE | `tests/test_promo_codes.py` | `sale10` сохраняется как `SALE10` |
| `is_currently_valid` | там же | inactive / expired → False |
| CRUD менеджер | `tests/test_promo_codes_api.py` | POST 201, GET by code |
| Клиент не создаёт | там же | 403 |
| lookup по code | там же | `/api/promo-codes/STACK10/` |

```python
# tests/test_promo_codes.py
from decimal import Decimal
import pytest
from django.utils import timezone
from datetime import timedelta
from promotions.models import PromoCode, PromoDiscountType


@pytest.mark.django_db
def test_code_uppercased_on_save():
    p = PromoCode.objects.create(
        code='sale10',
        discount_type=PromoDiscountType.PERCENT,
        value=Decimal('10'),
    )
    assert p.code == 'SALE10'


@pytest.mark.django_db
def test_expired_not_valid():
    p = PromoCode.objects.create(
        code='OLD',
        discount_type=PromoDiscountType.PERCENT,
        value=Decimal('10'),
        valid_to=timezone.now() - timedelta(days=1),
    )
    assert p.is_currently_valid() is False
```

```python
# tests/test_promo_codes_api.py
from decimal import Decimal
import pytest


@pytest.mark.django_db
def test_manager_promo_crud(manager_api, client_api):
    r = manager_api.post('/api/promo-codes/', {
        'code': 'stack10',
        'discount_type': 'PERCENT',
        'value': '10',
        'stackable_with_product_discounts': True,
        'is_active': True,
    }, format='json')
    assert r.status_code == 201
    assert r.data['code'] == 'STACK10'

    r = manager_api.get('/api/promo-codes/STACK10/')
    assert r.status_code == 200
    assert r.data['stackable_with_product_discounts'] is True

    r = client_api.post('/api/promo-codes/', {
        'code': 'HACK', 'discount_type': 'PERCENT', 'value': '50', 'is_active': True,
    }, format='json')
    assert r.status_code == 403
```

```bash
pytest tests/test_promo_codes.py tests/test_promo_codes_api.py
```

**Все пункты отмечены?** → [step-12-pricing-service.md](step-12-pricing-service.md)

# Шаг 9 — Скидки на отдельные товары

**Предыдущий:** [step-08-cart.md](step-08-cart.md) · **Следующий:** [step-10-promo-codes.md](step-10-promo-codes.md)

## Задача

Менеджер задаёт скидку на **определённые товары**. Клиент в каталоге/корзине должен видеть цену со скидкой (отображение — здесь; финальный расчёт заказа — шаг 11).

---

## Теория: отдельная модель vs поле на Product

| Подход | Плюсы | Минусы |
|--------|-------|--------|
| `Product.discount_percent` | просто | нет периода, истории, нескольких акций |
| `ProductDiscount` FK → Product | даты, активность, тип (% или сумма) | чуть больше кода |

Для ТЗ и суммирования с промокодом берём **ProductDiscount**.

Правило «одна активная скидка на товар»: либо `UniqueConstraint` по product среди active, либо в коде берём «лучшую» / «последнюю». В гайде — не больше одной активной на товар (валидация в serializer).

---

## 1. Модель — добавить в `catalog/models.py`

```python
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class DiscountType(models.TextChoices):
    PERCENT = 'PERCENT', 'Процент'
    FIXED = 'FIXED', 'Фиксированная сумма'


class ProductDiscount(models.Model):
    product = models.ForeignKey(
        Product,
        related_name='discounts',
        on_delete=models.CASCADE,
    )
    discount_type = models.CharField(
        max_length=16,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Процент (0–100) или сумма в валюте магазина',
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product}: {self.value} ({self.discount_type})'

    def is_currently_active(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def apply_to_price(self, price):
        """Вернуть цену после скидки (Decimal)."""
        from decimal import Decimal, ROUND_HALF_UP
        price = Decimal(price)
        if self.discount_type == DiscountType.PERCENT:
            # value=10 → минус 10%
            if self.value > 100:
                raise ValueError('Процент не может быть > 100')
            factor = (Decimal('100') - self.value) / Decimal('100')
            result = price * factor
        else:
            result = price - self.value
        if result < 0:
            result = Decimal('0')
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
```

Для процента добавьте валидатор в `clean` / serializer: `0 < value ≤ 100`.

```bash
python manage.py makemigrations catalog
python manage.py migrate
```

Admin:

```python
from .models import Category, Product, ProductDiscount


class ProductDiscountInline(admin.TabularInline):
    model = ProductDiscount
    extra = 0


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    # ... как было на шаге 4
    pass


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # ... как было
    inlines = [ProductDiscountInline]


@admin.register(ProductDiscount)
class ProductDiscountAdmin(admin.ModelAdmin):
    list_display = ('product', 'discount_type', 'value', 'is_active', 'starts_at', 'ends_at')
    list_filter = ('is_active', 'discount_type')
```

---

## 2. Хелпер «текущая скидка товара»

`catalog/services.py`:

```python
from .models import ProductDiscount


def get_active_discount(product):
    for d in product.discounts.all():
        if d.is_currently_active():
            return d
    return None


def get_effective_unit_price(product):
    discount = get_active_discount(product)
    if not discount:
        return product.price
    return discount.apply_to_price(product.price)
```

Чтобы не было N+1, в queryset используйте `prefetch_related('discounts')`.

---

## 3. API для менеджера

`catalog/serializers.py` — добавить:

```python
class ProductDiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDiscount
        fields = (
            'id', 'product', 'discount_type', 'value',
            'is_active', 'starts_at', 'ends_at', 'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def validate(self, attrs):
        dtype = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        if dtype == DiscountType.PERCENT and value is not None and value > 100:
            raise serializers.ValidationError({'value': 'Процент ≤ 100'})
        product = attrs.get('product', getattr(self.instance, 'product', None))
        is_active = attrs.get('is_active', True)
        if product and is_active:
            qs = ProductDiscount.objects.filter(product=product, is_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'У товара уже есть активная скидка — деактивируйте её'
                )
        return attrs
```

Не забудьте импорты `ProductDiscount`, `DiscountType`.

`catalog/views.py`:

```python
class ProductDiscountViewSet(viewsets.ModelViewSet):
    queryset = ProductDiscount.objects.select_related('product').all()
    serializer_class = ProductDiscountSerializer
    permission_classes = [IsManager]
```

Router:

```python
router.register('discounts', ProductDiscountViewSet, basename='discount')
```

---

## 4. Показать цену со скидкой в ProductSerializer

```python
from .services import get_active_discount, get_effective_unit_price


class ProductSerializer(serializers.ModelSerializer):
    effective_price = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            'id', 'category', 'name', 'slug', 'description', 'price',
            'effective_price', 'discount',
            'stock', 'is_active', 'image', 'created_at', 'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_effective_price(self, obj):
        return get_effective_unit_price(obj)

    def get_discount(self, obj):
        d = get_active_discount(obj)
        if not d:
            return None
        return ProductDiscountSerializer(d).data
```

В `ProductViewSet.get_queryset` добавьте `.prefetch_related('discounts')`.

Обновите `CartItemSerializer.get_line_total`, чтобы умножать на `get_effective_unit_price(obj.product)` — иначе корзина врёт.

---

## ✅ Ручная проверка

```bash
# менеджер создаёт скидку 20% на product 1
curl -s -X POST http://127.0.0.1:8000/api/discounts/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"product":1,"discount_type":"PERCENT","value":"20","is_active":true}' \
  | python -m json.tool

curl -s http://127.0.0.1:8000/api/products/1/ | python -m json.tool
# price=..., effective_price= на 20% меньше
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | POST discount менеджером | 201 |
| ☐ | GET product | `effective_price` меньше `price` |
| ☐ | Вторая активная скидка на тот же product | 400 |
| ☐ | Гость POST discount | 401/403 |
| ☐ | Корзина считает line_total по effective_price | сумма с учётом скидки |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| `apply_to_price` percent | `tests/test_discounts.py` | 100 − 20% = 80 |
| `get_effective_unit_price` | там же | без скидки = price |
| API create discount | `tests/test_discounts_api.py` | менеджер 201; в product есть `effective_price` |
| Вторая активная скидка | там же | 400 |
| Клиент POST discount | там же | 403 |

```python
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
```

```python
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
```

```bash
pytest tests/test_discounts.py tests/test_discounts_api.py
```

**Все пункты отмечены?** → [step-10-promo-codes.md](step-10-promo-codes.md)

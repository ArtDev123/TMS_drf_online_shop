# Шаг 4 — Модели товаров (catalog)

**Предыдущий:** [step-03-users-roles.md](step-03-users-roles.md) · **Следующий:** [step-05-products-api.md](step-05-products-api.md)

## Задача

Описать сущность «товар» в БД: название, описание, цена, активность. Без модели API CRUD на шаге 5 не к чему привязывать. Скидки вынесем в отдельную модель на шаге 9 — здесь только сам товар.

---

## Теория: деньги в Django

Для цены **никогда** не используйте `FloatField` — погрешность IEEE 754 сломает суммы корзины.

Используйте `DecimalField(max_digits=10, decimal_places=2)` и в Python работайте с `decimal.Decimal`, не с `float`.

В JSON DRF обычно отдаёт цену строкой `"199.99"` — это нормально и безопаснее.

---

## 1. Приложение `catalog`

```bash
python manage.py startapp catalog
```

Добавьте `'catalog'` в `INSTALLED_APPS`.

---

## 2. `catalog/models.py`

```python
from django.db import models


class Product(models.Model):
    name = models.CharField('название', max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField('описание', blank=True)
    price = models.DecimalField('цена', max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField('остаток', default=0)
    is_active = models.BooleanField('виден в каталоге', default=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'товар'
        verbose_name_plural = 'товары'

    def __str__(self):
        return self.name
```

**Разбор полей под ТЗ:**

| Поле | Зачем |
|------|--------|
| `name`, `description`, `price` | минимум витрины |
| `slug` | удобные URL / lookup; в API можно искать по slug |
| `stock` | задел под проверку qty в корзине (шаг 8) |
| `is_active` | менеджер «скрыл» товар — гость не видит (шаг 6) |
| `image` | опционально; нужен Pillow |
| `created_at` / `updated_at` | аудит в admin |

Скидки **не** кладём полем `discount_percent` на Product — у ТЗ отдельное управление скидками, плюс даты активности. Отдельная модель чище.

---

## 3. Admin — `catalog/admin.py`

```python
from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'stock', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'stock', 'is_active')
```

`prepopulated_fields` — в admin slug заполняется из названия (JS). В API менеджер может передать slug явно или мы сгенерируем в serializer (шаг 5).

---

## 4. Миграция + тестовые товары

```bash
python manage.py makemigrations catalog
python manage.py migrate
```

Shell:

```bash
python manage.py shell -c "
from decimal import Decimal
from catalog.models import Product
Product.objects.get_or_create(
    slug='tea-black',
    defaults={
        'name': 'Чёрный чай',
        'description': '100 г',
        'price': Decimal('12.50'),
        'stock': 100,
        'is_active': True,
    },
)
Product.objects.get_or_create(
    slug='coffee-arabica',
    defaults={
        'name': 'Кофе Arabica',
        'description': '250 г',
        'price': Decimal('25.00'),
        'stock': 50,
        'is_active': True,
    },
)
print(list(Product.objects.values_list('name', 'price')))
"
```

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `migrate catalog` | OK |
| ☐ | Admin → Товары | два товара видны |
| ☐ | Изменить `is_active=False` у одного | сохраняется |
| ☐ | Shell: `Product.objects.count()` | ≥ 2 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Создание Product | `tests/test_catalog_models.py` | сохраняется, `__str__`, slug unique |
| Цена Decimal | там же | не float; сравнение через `Decimal` |
| `is_active` по умолчанию | там же | `True` |

```python
# tests/test_catalog_models.py
from decimal import Decimal
import pytest
from django.db import IntegrityError
from catalog.models import Product


@pytest.mark.django_db
def test_create_product():
    p = Product.objects.create(
        name='Чай',
        slug='tea',
        price=Decimal('10.50'),
        stock=5,
    )
    assert p.is_active is True
    assert p.price == Decimal('10.50')
    assert str(p) == 'Чай'


@pytest.mark.django_db
def test_slug_unique():
    Product.objects.create(name='A', slug='same', price=Decimal('1.00'))
    with pytest.raises(IntegrityError):
        Product.objects.create(name='B', slug='same', price=Decimal('2.00'))
```

```bash
pytest tests/test_catalog_models.py
```

**Все пункты отмечены?** → [step-05-products-api.md](step-05-products-api.md)

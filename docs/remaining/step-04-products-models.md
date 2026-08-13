# Шаг 4 — Модели каталога: категории и товары

**Предыдущий:** [step-03-users-roles.md](step-03-users-roles.md) · **Следующий:** [step-05-products-api.md](step-05-products-api.md)

## Задача

Описать сущности «категория» и «товар» в БД. Товар принадлежит одной категории (many-to-one). Без моделей API CRUD на шаге 5 не к чему привязывать. Скидки вынесем в отдельную модель на шаге 10 — здесь только каталог.

```text
Category
  └── Product (FK category) → price, name, stock, is_active, …
```

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


class Category(models.Model):
    name = models.CharField('название', max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField('описание', blank=True)
    is_active = models.BooleanField('видна в каталоге', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'категория'
        verbose_name_plural = 'категории'

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='products',
        verbose_name='категория',
    )
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

**Разбор полей:**

| Поле / модель | Зачем |
|---------------|--------|
| `Category.name`, `slug`, `description` | группировка витрины; slug для URL / фильтра |
| `Category.is_active` | скрыть всю категорию (фильтр на шаге 6) |
| `Product.category` | FK many-to-one; `PROTECT` — нельзя удалить категорию с товарами |
| `related_name='products'` | `category.products.all()` |
| `name`, `description`, `price` | минимум витрины |
| `slug` | удобные URL / lookup; в API можно искать по slug |
| `stock` | задел под проверку qty в корзине (шаг 9) |
| `is_active` | менеджер «скрыл» товар — гость не видит (шаг 6) |
| `image` | опционально; нужен Pillow |
| `created_at` / `updated_at` | аудит в admin |

Скидки **не** кладём полем `discount_percent` на Product — у ТЗ отдельное управление скидками, плюс даты активности. Отдельная модель чище.

`on_delete=PROTECT` вместо `CASCADE`: случайно удалить категорию «Чай» и потерять все товары — плохой сценарий. Сначала перенесите товары или деактивируйте категорию.

---

## 3. Admin — `catalog/admin.py`

```python
from django.contrib import admin

from .models import Category, Product


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'updated_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'stock', 'is_active', 'updated_at')
    list_filter = ('is_active', 'category')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('price', 'stock', 'is_active')
    autocomplete_fields = ('category',)
```

`prepopulated_fields` — в admin slug заполняется из названия (JS). В API менеджер может передать slug явно или мы сгенерируем в serializer (шаг 5).

`autocomplete_fields` удобнее длинного `<select>`, когда категорий много (нужен `search_fields` у `CategoryAdmin`).

---

## 4. Миграция + тестовые данные

```bash
python manage.py makemigrations catalog
python manage.py migrate
```

Shell:

```bash
python manage.py shell -c "
from decimal import Decimal
from catalog.models import Category, Product

tea, _ = Category.objects.get_or_create(
    slug='tea',
    defaults={'name': 'Чай', 'is_active': True},
)
coffee, _ = Category.objects.get_or_create(
    slug='coffee',
    defaults={'name': 'Кофе', 'is_active': True},
)

Product.objects.get_or_create(
    slug='tea-black',
    defaults={
        'category': tea,
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
        'category': coffee,
        'name': 'Кофе Arabica',
        'description': '250 г',
        'price': Decimal('25.00'),
        'stock': 50,
        'is_active': True,
    },
)
print(list(Product.objects.values_list('name', 'category__name', 'price')))
"
```

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `migrate catalog` | OK |
| ☐ | Admin → Категории | «Чай», «Кофе» |
| ☐ | Admin → Товары | два товара с категориями |
| ☐ | Удалить категорию с товарами | ошибка `ProtectedError` |
| ☐ | Изменить `is_active=False` у товара | сохраняется |
| ☐ | Shell: `Product.objects.count()` | ≥ 2 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Создание Category / Product | `tests/test_catalog_models.py` | сохраняется, `__str__`, slug unique |
| Product → Category | там же | `product.category == cat`, `cat.products.count()` |
| Цена Decimal | там же | не float; сравнение через `Decimal` |
| `is_active` по умолчанию | там же | `True` |
| PROTECT | там же | удаление категории с товаром → `ProtectedError` |

```python
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
        category=category, name='A', slug='same', price=Decimal('1.00'),
    )
    with pytest.raises(IntegrityError):
        Product.objects.create(
            category=category, name='B', slug='same', price=Decimal('2.00'),
        )


@pytest.mark.django_db
def test_category_protect(category):
    Product.objects.create(
        category=category, name='X', slug='x', price=Decimal('1.00'),
    )
    with pytest.raises(ProtectedError):
        category.delete()
```

```bash
pytest tests/test_catalog_models.py
```

**Все пункты отмечены?** → [step-05-products-api.md](step-05-products-api.md)

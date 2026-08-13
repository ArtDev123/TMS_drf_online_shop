# Шаг 6 — Публичный каталог для гостя

**Предыдущий:** [step-05-products-api.md](step-05-products-api.md) · **Следующий:** [step-07-swagger.md](step-07-swagger.md)

## Задача

Незарегистрированный клиент может **просматривать** категории и товары. Клиент (с токеном) тоже. Создавать/менять/удалять — по-прежнему только менеджер.

---

## Теория: разные permissions на разные actions

На шаге 5 оба ViewSet (`CategoryViewSet`, `ProductViewSet`) закрыты одним списком:

```python
permission_classes = [IsManager]  # на ВСЕ actions одинаково
```

Так гость не может даже `GET` каталог — а по ТЗ должен. Значит permissions должны зависеть от **действия** (`self.action`), а не только от класса.

### `permission_classes` vs `get_permissions()`

| Способ | Когда |
|--------|--------|
| `permission_classes = [...]` | одно правило на все methods/actions |
| `get_permissions(self)` | вернуть **новый** список экземпляров permission в зависимости от `self.action` / метода |

DRF в `initial()` вызывает примерно:

```python
for permission in self.get_permissions():
    if not permission.has_permission(request, self):
        raise PermissionDenied / NotAuthenticated
```

`get_permissions` по умолчанию делает `[perm() for perm in self.permission_classes]`. Переопределяя метод, вы подменяете этот список.

### Правило для каталога

```python
def get_permissions(self):
    if self.action in ('list', 'retrieve'):
        return [AllowAny()]
    return [IsManager()]
```

| Action | Кто | HTTP |
|--------|-----|------|
| `list`, `retrieve` | все (гость, клиент, менеджер) | GET |
| `create`, `update`, `partial_update`, `destroy` | менеджер | POST/PUT/PATCH/DELETE |

Откуда берётся `self.action`: Router (или `as_view({...})`) записывает строку `'list'` / `'create'` / … в экземпляр ViewSet **до** вызова permission. Для кастомного `@action(detail=False)` имя action = имя метода (`add_item` и т.п.).

### Типичная ошибка

```python
# ПЛОХО — забыли скобки / вернули классы
return [AllowAny]          # нужен AllowAny()
# ПЛОХО — смотрите request.method вместо action
if request.method == 'GET' # GET бывает и list, и retrieve — ок; но PUT vs PATCH путают
```

Для ViewSet надёжнее именно `self.action`.

### 401 vs 403 — напоминание

| Код | Ситуация |
|-----|----------|
| **401** | не аутентифицирован (нет/битый JWT), а endpoint требует пользователя |
| **403** | пользователь известен, но `IsManager` / другая permission сказала «нет» |

`AllowAny` на `list` → гость получает **200**, не 401.

---

## Теория: `get_queryset` — разные данные разным ролям

Permissions отвечают «можно ли дернуть endpoint».  
`get_queryset` отвечает «**какие строки** отдать / среди каких искать pk».

Гость не должен видеть `is_active=False`. Менеджеру в CRUD удобно видеть все.

Два подхода:

1. Разный `get_queryset()` по роли — **наш выбор**.
2. Два ViewSet (public + manage) — больше кода, дубли serializers/urls.

```text
GET /api/products/          list() → get_queryset() → filter is_active
GET /api/products/99/       retrieve → get_object() → ищет в get_queryset()
                            если 99 скрыт и вы гость → 404 (не 403)
```

**Важно:** скрытый товар для гостя лучше отдавать как **404**, а не 403 — не светим существование id.

Рекомендация DRF: оставьте классовый `queryset = Product.objects.all()` (Router/basename/схема) и **всегда** фильтруйте в `get_queryset()`.

---

## Теория: `get_serializer_class` (задел)

Иногда гостю не нужны поля `stock` / `is_active`. Тогда:

```python
def get_serializer_class(self):
    if self.action in ('list', 'retrieve') and not (
        self.request.user.is_authenticated and self.request.user.is_manager
    ):
        return ProductListSerializer  # урезанный fields
    return ProductSerializer
```

Тот же приём, что с permissions: **разный контракт JSON на разные actions/роли**, один ViewSet. На минималках можно жить с одним serializer — см. опциональный блок ниже.

---

## 1. Обновить `CategoryViewSet` и `ProductViewSet`

`catalog/views.py`:

```python
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from accounts.permissions import IsManager
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Category.objects.all()
        user = self.request.user
        if user.is_authenticated and getattr(user, 'is_manager', False):
            return qs
        return qs.filter(is_active=True)


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related('category').all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Product.objects.select_related('category').all()
        user = self.request.user
        # менеджер видит всё, включая скрытые
        if not (user.is_authenticated and getattr(user, 'is_manager', False)):
            qs = qs.filter(is_active=True, category__is_active=True)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_id=category)
        return qs
```

Уберите классовый `queryset = …` **или** оставьте его для router basename / schema, но всегда перекрывайте через `get_queryset`. Рекомендация DRF: задать `queryset` для роутера и всё равно переопределить.

Фильтр `?category=1` — товары одной категории. Гость не видит товары из скрытых категорий (`category__is_active=True`).

---

## 2. (Опционально) поиск и фильтр цены

Установите при желании `django-filter` — или сделайте простой query-param вручную в `ProductViewSet.get_queryset` (после фильтра по роли):

```python
search = self.request.query_params.get('search')
if search:
    qs = qs.filter(name__icontains=search)
return qs
```

Пример: `GET /api/products/?search=чай` · `GET /api/products/?category=1`

---

## 3. Сериализатор «для витрины» (опционально)

Менеджеру нужны `stock`, `is_active`. Гостю — можно урезать. Через `get_serializer_class`:

```python
class ProductListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'category', 'name', 'slug', 'description', 'price', 'image')


class ProductViewSet(viewsets.ModelViewSet):
    # ...
    def get_serializer_class(self):
        user = self.request.user
        if self.action in ('list', 'retrieve') and not (
            user.is_authenticated and getattr(user, 'is_manager', False)
        ):
            return ProductListSerializer
        return ProductSerializer
```

На минималках можно оставить один `ProductSerializer` — лишние поля гостю не вредят.

---

## ✅ Ручная проверка

```bash
# гость
curl -s http://127.0.0.1:8000/api/categories/ | python -m json.tool
curl -s http://127.0.0.1:8000/api/products/ | python -m json.tool
curl -s 'http://127.0.0.1:8000/api/products/?category=1' | python -m json.tool

# спрятать товар в admin (is_active=False) и снова GET без токена —
# товара не должно быть в results

# POST гостем
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/api/products/ \
  -H 'Content-Type: application/json' \
  -d '{"category":1,"name":"X","slug":"x","price":"1.00"}'
# 401
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | GET `/api/categories/` без токена | 200, активные категории |
| ☐ | GET `/api/products/` без токена | 200, активные товары |
| ☐ | GET `?category=<id>` | только товары этой категории |
| ☐ | Товар с `is_active=False` | не виден гостю |
| ☐ | Менеджер с токеном GET | видит и неактивные |
| ☐ | POST без токена | 401 |
| ☐ | POST с токеном менеджера | 201 |

---

## 🧪 Покрытие тестами

После смены `get_permissions` обновите/добавьте тесты — старый `test_list_requires_auth` (401) **должен упасть**: теперь гость читает каталог.

| Что | Файл | Проверка |
|-----|------|----------|
| Гость list категорий/товаров | `tests/test_catalog_public.py` | GET → 200 |
| Скрытый товар | там же | `is_active=False` не в `results` |
| Фильтр `?category=` | там же | только нужная категория |
| Гость retrieve скрытого | там же | 404 |
| Менеджер видит скрытый | там же | 200 |
| Гость POST | там же | 401 |
| Клиент POST | там же | 403 |

```python
# tests/test_catalog_public.py
from decimal import Decimal
import pytest
from catalog.models import Category, Product


@pytest.fixture
def category(db):
    return Category.objects.create(name='Витрина', slug='vitrina-cat')


@pytest.fixture
def active_product(category):
    return Product.objects.create(
        category=category,
        name='Витрина', slug='vitrina', price=Decimal('5.00'), stock=3, is_active=True,
    )


@pytest.fixture
def hidden_product(category):
    return Product.objects.create(
        category=category,
        name='Скрытый', slug='hidden', price=Decimal('5.00'), stock=3, is_active=False,
    )


@pytest.mark.django_db
def test_guest_sees_categories(api, category):
    r = api.get('/api/categories/')
    assert r.status_code == 200
    ids = [row['id'] for row in r.data['results']]
    assert category.id in ids


@pytest.mark.django_db
def test_guest_sees_active(api, active_product, hidden_product):
    r = api.get('/api/products/')
    assert r.status_code == 200
    ids = [row['id'] for row in r.data['results']]
    assert active_product.id in ids
    assert hidden_product.id not in ids


@pytest.mark.django_db
def test_filter_by_category(api, active_product, category):
    other = Category.objects.create(name='Другая', slug='other')
    Product.objects.create(
        category=other, name='Y', slug='y', price=Decimal('1.00'), stock=1,
    )
    r = api.get(f'/api/products/?category={category.id}')
    assert all(row['category'] == category.id for row in r.data['results'])
    assert active_product.id in [row['id'] for row in r.data['results']]


@pytest.mark.django_db
def test_guest_hidden_retrieve_404(api, hidden_product):
    assert api.get(f'/api/products/{hidden_product.id}/').status_code == 404


@pytest.mark.django_db
def test_manager_sees_hidden(manager_api, hidden_product):
    assert manager_api.get(f'/api/products/{hidden_product.id}/').status_code == 200


@pytest.mark.django_db
def test_guest_cannot_post(api, category):
    r = api.post('/api/products/', {
        'category': category.pk,
        'name': 'X', 'slug': 'x2', 'price': '1.00', 'stock': 1, 'is_active': True,
    }, format='json')
    assert r.status_code in (401, 403)
```

```bash
pytest tests/test_catalog_public.py
# удалите или поправьте устаревший test_list_requires_auth из шага 5
```

**Все пункты отмечены?** → [step-07-swagger.md](step-07-swagger.md)

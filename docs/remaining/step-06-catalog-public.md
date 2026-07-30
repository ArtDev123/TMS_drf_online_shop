# Шаг 6 — Публичный каталог для гостя

**Предыдущий:** [step-05-products-api.md](step-05-products-api.md) · **Следующий:** [step-07-registration-email.md](step-07-registration-email.md)

## Задача

Незарегистрированный клиент может **просматривать** товары. Клиент (с токеном) тоже. Создавать/менять/удалять — по-прежнему только менеджер.

---

## Теория: разные permissions на разные actions

На шаге 5 весь `ProductViewSet` закрыт одним списком:

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

## 1. Обновить `ProductViewSet`

`catalog/views.py`:

```python
from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from accounts.permissions import IsManager
from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Product.objects.all()
        user = self.request.user
        # менеджер видит всё, включая скрытые
        if user.is_authenticated and getattr(user, 'is_manager', False):
            return qs
        return qs.filter(is_active=True)
```

Уберите классовый `queryset = …` **или** оставьте его для router basename / schema, но всегда перекрывайте через `get_queryset`. Рекомендация DRF: задать `queryset` для роутера и всё равно переопределить:

```python
queryset = Product.objects.all()
```

---

## 2. (Опционально) поиск и фильтр цены

Установите при желании `django-filter` — или сделайте простой query-param вручную:

```python
def get_queryset(self):
    qs = super().get_queryset() if hasattr(super(), 'get_queryset') else Product.objects.all()
    # перепишите целиком как выше + :
    user = self.request.user
    if user.is_authenticated and getattr(user, 'is_manager', False):
        qs = Product.objects.all()
    else:
        qs = Product.objects.filter(is_active=True)

    search = self.request.query_params.get('search')
    if search:
        qs = qs.filter(name__icontains=search)
    return qs
```

Пример: `GET /api/products/?search=чай`

---

## 3. Сериализатор «для витрины» (опционально)

Менеджеру нужны `stock`, `is_active`. Гостю — можно урезать. Через `get_serializer_class`:

```python
class ProductListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'name', 'slug', 'description', 'price', 'image')


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
curl -s http://127.0.0.1:8000/api/products/ | python -m json.tool

# спрятать товар в admin (is_active=False) и снова GET без токена —
# товара не должно быть в results

# POST гостем
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8000/api/products/ \
  -H 'Content-Type: application/json' \
  -d '{"name":"X","slug":"x","price":"1.00"}'
# 401
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | GET без токена | 200, активные товары |
| ☐ | Товар с `is_active=False` | не виден гостю |
| ☐ | Менеджер с токеном GET | видит и неактивные |
| ☐ | POST без токена | 401 |
| ☐ | POST с токеном менеджера | 201 |

---

## 🧪 Покрытие тестами

После смены `get_permissions` обновите/добавьте тесты — старый `test_list_requires_auth` (401) **должен упасть**: теперь гость читает каталог.

| Что | Файл | Проверка |
|-----|------|----------|
| Гость list | `tests/test_catalog_public.py` | GET → 200 |
| Скрытый товар | там же | `is_active=False` не в `results` |
| Гость retrieve скрытого | там же | 404 |
| Менеджер видит скрытый | там же | 200 |
| Гость POST | там же | 401 |
| Клиент POST | там же | 403 |

```python
# tests/test_catalog_public.py
from decimal import Decimal
import pytest
from catalog.models import Product


@pytest.fixture
def active_product(db):
    return Product.objects.create(
        name='Витрина', slug='vitrina', price=Decimal('5.00'), stock=3, is_active=True,
    )


@pytest.fixture
def hidden_product(db):
    return Product.objects.create(
        name='Скрытый', slug='hidden', price=Decimal('5.00'), stock=3, is_active=False,
    )


@pytest.mark.django_db
def test_guest_sees_active(api, active_product, hidden_product):
    r = api.get('/api/products/')
    assert r.status_code == 200
    ids = [row['id'] for row in r.data['results']]
    assert active_product.id in ids
    assert hidden_product.id not in ids


@pytest.mark.django_db
def test_guest_hidden_retrieve_404(api, hidden_product):
    assert api.get(f'/api/products/{hidden_product.id}/').status_code == 404


@pytest.mark.django_db
def test_manager_sees_hidden(manager_api, hidden_product):
    assert manager_api.get(f'/api/products/{hidden_product.id}/').status_code == 200


@pytest.mark.django_db
def test_guest_cannot_post(api):
    r = api.post('/api/products/', {
        'name': 'X', 'slug': 'x2', 'price': '1.00', 'stock': 1, 'is_active': True,
    }, format='json')
    assert r.status_code in (401, 403)
```

```bash
pytest tests/test_catalog_public.py
# удалите или поправьте устаревший test_list_requires_auth из шага 5
```

**Все пункты отмечены?** → [step-07-registration-email.md](step-07-registration-email.md)

# Шаг 5 — API товаров для менеджера (ViewSet + Router)

**Предыдущий:** [step-04-products-models.md](step-04-products-models.md) · **Следующий:** [step-06-catalog-public.md](step-06-catalog-public.md)

## Задача

Менеджер магазина может **просматривать, создавать, редактировать и удалять** товары через REST API. Это прямой пункт ТЗ.

На этом шаге весь ViewSet защитим `IsManager`. Публичное чтение для гостя откроем на шаге 6 через `get_permissions()`.

---

## Теория: ModelSerializer + ModelViewSet + Router

```text
Product  ←→  ProductSerializer  ←→  JSON
                ↑
         ProductViewSet
                ↑
         DefaultRouter → /api/products/
```

На шаге 2 вы уже знаете `Serializer` + `APIView` + ручной `path`. Здесь тот же конвейер, но:

- serializer **привязан к модели** (`ModelSerializer`);
- view умеет **весь CRUD** (`ModelViewSet`);
- URL **генерирует Router**, а не вы руками.

`ModelViewSet` уже реализует:

| Action | HTTP | URL | Что внутри (упрощённо) |
|--------|------|-----|------------------------|
| `list` | GET | `/api/products/` | `queryset` → serializer(many=True) |
| `create` | POST | `/api/products/` | serializer(data) → is_valid → save |
| `retrieve` | GET | `/api/products/{pk}/` | get_object() → serializer |
| `update` | PUT | `/api/products/{pk}/` | полная замена полей |
| `partial_update` | PATCH | `/api/products/{pk}/` | частичное обновление |
| `destroy` | DELETE | `/api/products/{pk}/` | get_object() → delete |

Вам не нужно писать шесть методов вручную — только serializer, queryset, permissions.

---

## Теория: ViewSet — зачем и как устроен

### Проблема, которую решает ViewSet

На `APIView` для CRUD товара пришлось бы писать что-то вроде:

```python
class ProductListCreate(APIView):
    def get(self, request): ...
    def post(self, request): ...

class ProductDetail(APIView):
    def get(self, request, pk): ...
    def put(self, request, pk): ...
    def patch(self, request, pk): ...
    def delete(self, request, pk): ...
```

И два (или больше) `path(...)`. **ViewSet** собирает все действия в один класс с «логическими» именами (`list`, `create`…), а **Router** разводит их по URL и HTTP-методам.

### Иерархия классов (от простого к полному)

```text
ViewSet
  └── GenericViewSet          (+ get_queryset, get_serializer, get_object)
        ├── ReadOnlyModelViewSet   = list + retrieve
        └── ModelViewSet           = list + create + retrieve + update + destroy
```

| Класс | Когда брать |
|-------|-------------|
| `ViewSet` | совсем кастомные действия (`@action`), сами пишете методы |
| `GenericViewSet` + mixins | нужен кусок CRUD, не весь (например только list+create) |
| `ReadOnlyModelViewSet` | каталог «только читать» |
| `ModelViewSet` | полный CRUD ресурса (товары, скидки, промокоды) |

Mixins, из которых склеен `ModelViewSet`:

- `ListModelMixin` → `list`
- `CreateModelMixin` → `create`
- `RetrieveModelMixin` → `retrieve`
- `UpdateModelMixin` → `update` / `partial_update`
- `DestroyModelMixin` → `destroy`

Можно собрать узкий ViewSet: `class X(mixins.ListModelMixin, mixins.CreateModelMixin, GenericViewSet)`.

### Action ≠ HTTP-метод

В `APIView` метод класса = HTTP (`post`).  
В `ViewSet` метод класса = **действие** (`create`), а HTTP к нему привязывает Router:

```text
POST /api/products/     →  action «create»  →  ProductViewSet.create()
GET  /api/products/5/   →  action «retrieve» → ProductViewSet.retrieve()
```

Имя текущего действия доступно как `self.action` — на шаге 6 по нему разведём permissions (чтение всем, запись менеджеру).

### Что обязано быть у ModelViewSet

```python
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()       # или get_queryset()
    serializer_class = ProductSerializer   # или get_serializer_class()
    permission_classes = [IsManager]
    lookup_field = 'pk'                    # поле в URL: /products/<pk>/
```

| Атрибут | Роль |
|---------|------|
| `queryset` | откуда брать объекты; Router также смотрит на него для basename |
| `serializer_class` | какой serializer для входа/выхода |
| `permission_classes` | список проверок до action |
| `lookup_field` | по какому полю искать объект (`pk` или `slug`) |
| `pagination_class` | можно переопределить пагинацию только здесь |

### `get_object()` — откуда берётся товар с id=5

1. Из URL извлекается `pk` (имя зависит от `lookup_url_kwarg` / `lookup_field`).
2. `get_queryset().get(pk=5)` (через `get_object_or_404`-логику DRF).
3. `check_object_permissions` — object-level permission, если есть.
4. Дальше `retrieve` / `update` / `destroy` работают с этим объектом.

Если товара нет → **404**, не 500.

### Поток `create` внутри ModelViewSet (то же, что вы писали руками)

```text
POST /api/products/  + JSON body
        │
        ▼
permission_classes OK?
        │
        ▼
get_serializer(data=request.data)
        │
        ▼
serializer.is_valid(raise_exception=True)
        │
        ▼
perform_create(serializer)  →  по умолчанию serializer.save()
        │                      →  ModelSerializer.create(validated_data)
        ▼
Response(serializer.data, status=201)
```

`perform_create` часто переопределяют, чтобы подставить `request.user`:

```python
def perform_create(self, serializer):
    serializer.save(owner=self.request.user)
```

У товаров владельца нет — дефолтного `save()` достаточно.

### ViewSet без Router — тоже можно

```python
path('products/', ProductViewSet.as_view({
    'get': 'list',
    'post': 'create',
}))
path('products/<int:pk>/', ProductViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
}))
```

Словарь `{http_method: action_name}` — ручной аналог того, что делает Router. Router просто не даёт ошибиться в этом словаре.

---

## Теория: ModelSerializer — глубже, чем на шаге 2

### Что генерирует `Meta`

```python
class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ('id', 'name', 'slug', 'price', ...)
        read_only_fields = ('id', 'created_at', 'updated_at')
```

DRF смотрит на поля модели и создаёт соответствующие serializer-поля:

| Поле модели | Поле serializer |
|-------------|-----------------|
| `CharField` | `CharField` |
| `DecimalField` | `DecimalField` |
| `BooleanField` | `BooleanField` |
| `ForeignKey` | `PrimaryKeyRelatedField` (по умолчанию) |
| `DateTimeField` | `DateTimeField` |

`fields = '__all__'` можно, но в учебном проекте лучше **явный кортеж** — видно контракт API.

### `read_only_fields` vs `extra_kwargs`

- `read_only_fields` — клиент не может задать `id` / timestamps при POST.
- Для тонкой настройки:

```python
extra_kwargs = {
    'slug': {'required': False},
    'stock': {'min_value': 0},
}
```

### `create` / `update` из коробки

```python
# внутри ModelSerializer после is_valid:
serializer.save()
# → если instance не было:  create(validated_data) → Product.objects.create(**validated_data)
# → если instance был:      update(instance, validated_data) → setattr + save()
```

Переопределяете `create`/`update` в serializer, когда нужно:

- создать связанные объекты;
- вытащить поле и обработать отдельно (пароль → `set_password`);
- игнорировать лишние ключи.

ViewSet сам вызывает `save()`; вам в action обычно не нужно вызывать `Product.objects.create` вручную.

### Валидация на ModelSerializer

```python
def validate_price(self, value):
    # одно поле; value уже приведено к Decimal
    ...

def validate(self, attrs):
    # несколько полей сразу; attrs — dict
    if attrs.get('stock', 0) < 0:
        raise serializers.ValidationError(...)
    return attrs
```

Ошибки одного поля → `{"price": ["…"]}`.  
Ошибки из `validate` → `{"non_field_errors": ["…"]}` или ваш ключ, если передали dict.

### Сериализация выхода в list/retrieve

```python
ProductSerializer(product).data
ProductSerializer(queryset, many=True).data
```

`ModelViewSet.list` делает второе; `retrieve` — первое. Пагинация оборачивает список в `{count, next, previous, results}` — см. конец шага.

---

## Теория: Router и URL — как из ViewSet получаются пути

### `DefaultRouter` vs `SimpleRouter`

| | `SimpleRouter` | `DefaultRouter` |
|---|----------------|-----------------|
| `/products/` + `/products/{pk}/` | да | да |
| Корневой `/api/` со списком ссылок | нет | да (удобно в учёбе) |

В проекте используем `DefaultRouter`.

### Что делает `register`

```python
router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')
urlpatterns = router.urls
```

| Аргумент | Смысл |
|----------|--------|
| `'products'` | префикс URL (без слэшей по краям) |
| `ProductViewSet` | класс (не экземпляр!) |
| `basename='product'` | префикс имён: `product-list`, `product-detail` |

`basename` обязателен, если у ViewSet нет `.queryset` (Router иначе не угадает имя модели). С queryset можно не писать — но явное имя яснее.

### Какие URL появляются

После `path('api/', include(router.urls))`:

```text
GET/POST          /api/products/
GET/PUT/PATCH/DELETE  /api/products/<pk>/
GET               /api/                 ← только DefaultRouter: каталог эндпоинтов
```

Имена для `reverse`:

```python
reverse('product-list')                 # /api/products/
reverse('product-detail', kwargs={'pk': 1})  # /api/products/1/
```

Префикс `api/` зависит от того, как вы сделали `include` в `config/urls.py`.

### Связка config → app → router

```text
config/urls.py
  path('api/', include('catalog.urls'))
        │
        ▼
catalog/urls.py
  router.register('products', ProductViewSet)
  urlpatterns = router.urls
        │
        ▼
Итог: /api/ + products/ + [pk/]
```

Несколько приложений:

```python
path('api/', include('core.urls')),      # /api/health/, /api/echo/
path('api/', include('catalog.urls')), # /api/products/
path('api/', include('cart.urls')),    # /api/cart/
```

Все делят префикс `/api/`. Имена ресурсов (`products`, `cart`) не должны пересекаться.

### Lookup: `pk` vs `slug`

```python
lookup_field = 'slug'
# URL станет /api/products/tea-black/  вместо /api/products/1/
```

Тогда в `reverse` передаёте `slug=...`. На этом шаге оставляем `pk` — проще для curl.

### `@action` — свои URL на ViewSet (задел)

```python
from rest_framework.decorators import action

@action(detail=True, methods=['post'])
def archive(self, request, pk=None):
    ...
# → POST /api/products/{pk}/archive/
```

`detail=False` → `/api/products/archive/` (без pk). Корзина на шаге 8 как раз использует `@action`.

### Как отладить маршруты

```bash
python manage.py show_urls  # если установлен django-extensions
# или
python manage.py shell -c "
from django.urls import get_resolver
for p in get_resolver().url_patterns:
    print(p)
"
```

В browsable API корень `/api/` (DefaultRouter) тоже показывает список ресурсов.

---

## 1. Serializer — `catalog/serializers.py`

```python
from rest_framework import serializers

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'price',
            'stock',
            'is_active',
            'image',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Цена должна быть больше 0')
        return value
```

**Разбор (привязка к теории выше):**

- `ModelSerializer` сам строит поля по модели и умеет `.create()` / `.update()` — ViewSet вызовет `serializer.save()` за вас.
- `fields = (…)`, не `__all__` — явный контракт JSON для фронта/Postman.
- `read_only_fields` — клиент не подделает `id` и timestamps в POST/PATCH.
- `validate_price` — шаг 2 цепочки валидации (после приведения типа поля, до `validate()`).
- Ошибка → HTTP **400** и тело вида `{"price": ["Цена должна быть больше 0"]}`.

Попробуйте в shell (без HTTP):

```bash
python manage.py shell -c "
from catalog.serializers import ProductSerializer
s = ProductSerializer(data={'name': 'X', 'slug': 'x', 'price': '-1', 'stock': 1})
print(s.is_valid(), s.errors)
"
```

---

## 2. ViewSet — `catalog/views.py`

```python
from rest_framework import viewsets

from accounts.permissions import IsManager
from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    CRUD товаров.
    Пока весь набор действий — только для менеджера.
    На шаге 6 откроем list/retrieve для всех.
    """

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [IsManager]
    lookup_field = 'pk'  # можно сменить на 'slug'
```

**Разбор:**

- Четыре строки вместо шести `APIView` + ручных `path` — смысл ViewSet.
- `queryset` — источник для `list`/`get_object`; на шаге 6 сузим через `get_queryset()`.
- `serializer_class` — один на все actions; позже можно `get_serializer_class()` (короткий список для гостя).
- `permission_classes = [IsManager]` — **все** actions закрыты; без токена обычно **401**, с токеном клиента — **403**.
- Гость каталог пока не увидит — шаг 6 (`get_permissions` + `self.action`).
- `lookup_field = 'pk'` — в URL числовой id; см. теорию про slug выше.

Эквивалент «вручную без Router» (не копируйте в проект — для понимания):

```python
ProductViewSet.as_view({'get': 'list', 'post': 'create'})
ProductViewSet.as_view({
    'get': 'retrieve', 'put': 'update',
    'patch': 'partial_update', 'delete': 'destroy',
})
```

---

## 3. Router — `catalog/urls.py`

```python
from rest_framework.routers import DefaultRouter

from .views import ProductViewSet

router = DefaultRouter()
router.register('products', ProductViewSet, basename='product')

urlpatterns = router.urls
```

В `config/urls.py` добавьте:

```python
path('api/', include('catalog.urls')),
```

рядом с уже существующим `path('api/', include('core.urls'))` — Django склеит оба include. Либо соберите один `api_urlpatterns`.

**Разбор URL-цепочки (повторение теории шага 2 + Router):**

```text
GET /api/products/1/
     │
     ├─ config: path('api/', include('catalog.urls'))
     ├─ router:  products/<pk>/  →  action=retrieve
     └─ ProductViewSet.retrieve → ProductSerializer(instance) → JSON
```

`register('products', …)` создаёт как минимум:

- `^products/$` → list/create  
- `^products/(?P<pk>[^/.]+)/$` → retrieve/update/partial_update/destroy  

плюс у `DefaultRouter` — корень со списком эндпоинтов. Имена: `product-list`, `product-detail`.

Проверка зарегистрированных путей:

```bash
python manage.py shell -c "
from catalog.urls import router
for u in router.urls:
    print(u.pattern, u.name)
"
```

---

## 4. Проверка через curl

Получите токен менеджера:

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"manager@shop.local","password":"manager123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access'])")
echo "$TOKEN"
```

Список:

```bash
curl -s http://127.0.0.1:8000/api/products/ \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Создание:

```bash
curl -s -X POST http://127.0.0.1:8000/api/products/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "Кружка",
    "slug": "mug-white",
    "description": "Белая керамика",
    "price": "9.90",
    "stock": 30,
    "is_active": true
  }' | python -m json.tool
```

Обновление цены:

```bash
curl -s -X PATCH http://127.0.0.1:8000/api/products/1/ \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"price": "11.00"}' | python -m json.tool
```

Удаление (осторожно с id):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE \
  http://127.0.0.1:8000/api/products/3/ \
  -H "Authorization: Bearer $TOKEN"
```

Без токена:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/products/
# ожидайте 401
```

---

## Теория: что возвращает paginator

При `PAGE_SIZE = 20` ответ `list` выглядит так:

```json
{
  "count": 3,
  "next": null,
  "previous": null,
  "results": [ { "id": 1, "name": "…" }, … ]
}
```

Клиент должен читать `results`, не корень массива. В browsable API это видно сразу.

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | GET `/api/products/` без токена | 401 |
| ☐ | GET с токеном менеджера | 200, список / `results` |
| ☐ | POST новый товар | 201, объект в ответе |
| ☐ | PATCH цены | 200, цена обновилась |
| ☐ | DELETE | 204 |
| ☐ | Токен клиента (если уже есть) на POST | 403 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Список без токена | `tests/test_products_api.py` | 401 (пока весь ViewSet = IsManager) |
| CRUD менеджером | там же | POST 201, PATCH 200, DELETE 204 |
| Клиент не создаёт | там же | POST → 403 |
| Валидация цены | `tests/test_product_serializer.py` | `price <= 0` → invalid |

Добавьте в `conftest.py` хелпер авторизации:

```python
# дополнение к tests/conftest.py
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


@pytest.fixture
def api():
    return APIClient()


def auth_client(user):
    api = APIClient()
    token = RefreshToken.for_user(user).access_token
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api


@pytest.fixture
def manager_api(manager):
    return auth_client(manager)


@pytest.fixture
def client_api(client_user):
    return auth_client(client_user)
```

```python
# tests/test_products_api.py
from decimal import Decimal
import pytest
from catalog.models import Product


@pytest.mark.django_db
def test_list_requires_auth(api):
    assert api.get('/api/products/').status_code == 401


@pytest.mark.django_db
def test_manager_crud(manager_api):
    r = manager_api.post('/api/products/', {
        'name': 'Кружка',
        'slug': 'mug',
        'description': '',
        'price': '9.90',
        'stock': 10,
        'is_active': True,
    }, format='json')
    assert r.status_code == 201
    pk = r.data['id']

    r = manager_api.patch(f'/api/products/{pk}/', {'price': '11.00'}, format='json')
    assert r.status_code == 200
    assert Decimal(r.data['price']) == Decimal('11.00')

    r = manager_api.delete(f'/api/products/{pk}/')
    assert r.status_code == 204
    assert not Product.objects.filter(pk=pk).exists()


@pytest.mark.django_db
def test_client_cannot_create(client_api):
    r = client_api.post('/api/products/', {
        'name': 'X', 'slug': 'x', 'price': '1.00', 'stock': 1, 'is_active': True,
    }, format='json')
    assert r.status_code == 403
```

```bash
pytest tests/test_products_api.py tests/test_product_serializer.py
```

**Все пункты отмечены?** → [step-06-catalog-public.md](step-06-catalog-public.md)

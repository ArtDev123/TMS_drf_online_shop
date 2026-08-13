# Шаг 2 — Теория DRF и первый endpoint

**Предыдущий:** [step-01-env.md](step-01-env.md) · **Следующий:** [step-03-users-roles.md](step-03-users-roles.md)

## Задача

Понять, **как устроен Django REST Framework**, подключить его в настройки и сделать «Hello API» — один рабочий JSON-endpoint. На следующих шагах вы будете только наращивать эту схему.

---

## Теория: REST за 5 минут

**REST API** — способ общаться с сервером через HTTP:

| Метод | Смысл | Пример |
|-------|--------|--------|
| `GET` | прочитать | список товаров |
| `POST` | создать | добавить товар / положить в корзину |
| `PUT` / `PATCH` | заменить / частично обновить | изменить цену |
| `DELETE` | удалить | убрать товар |

Клиент (браузер, Postman, мобильное приложение) шлёт запрос → сервер отвечает **JSON** и **статус-кодом** (`200`, `201`, `400`, `401`, `403`, `404`).

В классическом Django view обычно рендерит HTML. В DRF view сериализует данные в JSON.

---

## Теория: три кита DRF

```text
Serializer  —  «переводчик» Model ↔ JSON (+ валидация входа)
APIView / ViewSet  —  «что делать» с запросом (как view)
Router + urls  —  «на какой URL повесить» ViewSet
```

Ниже — подробно про каждый слой. ViewSet и Router по-настоящему понадобятся на шаге 5; здесь вы освоите **Serializer + APIView + ручные URL** — фундамент, на котором всё остальное стоит.

---

## Теория: как работает URL в Django / DRF

Запрос никогда не «находит view сам». Django идёт по списку `urlpatterns` **сверху вниз** и берёт **первое** совпадение.

```text
Браузер:  GET http://127.0.0.1:8000/api/health/
                    │
                    ▼
config/urls.py
  path('api/', include('core.urls'))     ← отрезает префикс «api/»
                    │
                    ▼
core/urls.py  (остаток пути: «health/»)
  path('health/', HealthView.as_view())  ← совпало
                    │
                    ▼
HealthView.dispatch → HealthView.get(request)
```

### `path`, `include`, `as_view`

| Конструкция | Что делает |
|-------------|------------|
| `path('health/', …)` | шаблон куска URL; `health/` должно совпасть целиком |
| `include('core.urls')` | «подключи другой список маршрутов»; префикс снаружи уже снят |
| `ClassName.as_view()` | **обязательно** для class-based view: превращает класс в callable-функцию, которую Django может вызвать |

Без `.as_view()` Django получит класс, а не функцию — будет ошибка.

### Почему `name='health'`

Имя нужно, чтобы в коде/тестах писать `reverse('health')` → `'/api/health/'`, а не хардкодить строку. В DRF с Router имена генерятся сами (`product-list`, `product-detail`) — об этом на шаге 5.

### Два способа повесить view

**1. Вручную (этот шаг):**

```python
path('echo/', EchoView.as_view(), name='echo')
```

Вы сами решаете: какой путь, какой HTTP-метод обработает view (`get` / `post`).

**2. Через Router (шаг 5):**

```python
router.register('products', ProductViewSet)
# сам создаст /products/ и /products/{pk}/
```

Router — не магия, а генератор тех же `path(...)`, только пачкой под CRUD.

### Порядок `include` важен

```python
path('api/', include('core.urls')),
path('api/', include('catalog.urls')),
```

Оба живут под `/api/`. Django сначала ищет в `core`, потом в `catalog`. Если в двух приложениях одинаковый хвост (`products/`), победит первый — не дублируйте имена ресурсов.

### Request доходит до view так

```text
1. Django URL resolver выбрал view
2. Middleware (сессии, auth, CSRF…)
3. view(request)  — для CBV это результат as_view()
4. У APIView внутри: authenticate → check permissions → get/post/...
5. Response → рендер JSON или browsable HTML
```

---

## Теория: Serializer подробно

Без DRF вы бы писали:

```python
json.dumps({'id': product.id, 'name': product.name, 'price': str(product.price)})
```

и руками проверяли вход. Serializer делает **оба** направления и валидацию.

### Два режима одного класса

| Режим | Как создаёте | Что происходит |
|-------|--------------|----------------|
| **Сериализация (выход)** | `Serializer(instance=product)` или `Serializer(qs, many=True)` | объект → Python dict → JSON в `Response` |
| **Десериализация (вход)** | `Serializer(data=request.data)` | JSON → проверка полей → `validated_data` |

Ключ: при **входе** всегда передаёте `data=...`. При **выходе** — объект/`instance` (или queryset + `many=True`). Перепутаете — получите пустые/`invalid` данные.

```python
# ВЫХОД — отдать товар клиенту
ser = ProductSerializer(product)
ser.data          # {'id': 1, 'name': '...', ...}  — уже готово к Response

# ВХОД — принять JSON от клиента
ser = ProductSerializer(data=request.data)
ser.is_valid()    # True/False
ser.validated_data  # только после is_valid()!
ser.errors        # {'price': ['…']} если невалидно
```

### `Serializer` vs `ModelSerializer`

| | `serializers.Serializer` | `serializers.ModelSerializer` |
|---|--------------------------|-------------------------------|
| Поля | пишете руками | почти все берёт из модели |
| `.create()` / `.update()` | пишете сами (или не нужны) | генерируются из `Meta.model` |
| Когда | формы без модели, echo, login, «склейка» нескольких моделей | CRUD одной модели (товар, скидка, промокод) |

На этом шаге — обычный `Serializer` (Echo). На шаге 5 — `ModelSerializer` для Product.

### Жизненный цикл валидации (вход)

```text
request.data  (dict из JSON)
      │
      ▼
Serializer(data=...)
      │
      ▼
is_valid()
  1. to_internal_value  — каждое поле: CharField, DecimalField…
  2. validate_<fieldname>(value)  — ваша проверка одного поля
  3. validate(attrs)  — кросс-полевая (password == password_confirm)
      │
      ├─ OK  → validated_data
      └─ fail → errors; при raise_exception=True → HTTP 400
```

**Правило:** после успешного `is_valid()` для бизнес-логики используйте **только** `validated_data`, не сырой `request.data`. Иначе обойдёте свои же проверки.

### Поля, которые часто встретите

| Поле DRF | Аналог | Заметка |
|----------|--------|---------|
| `CharField` | строка | `max_length`, `allow_blank` |
| `EmailField` | email | форматная проверка |
| `IntegerField` / `DecimalField` | числа | для денег — Decimal |
| `BooleanField` | bool | |
| `PrimaryKeyRelatedField` | FK по id | `queryset=Product.objects.all()` |
| `SerializerMethodField` | вычисляемое | только чтение, метод `get_<имя>` |
| `read_only=True` | | в JSON уйдёт, из входа игнорируется |
| `write_only=True` | | принимается на входе, в ответе не светится (пароль!) |

### `many=True`

Один объект vs список:

```python
ProductSerializer(product).data           # dict
ProductSerializer(products, many=True).data  # list[dict]
```

Без `many=True` на queryset будет ошибка / бессмыслица.

### Связка serializer ↔ view (паттерн на весь курс)

```python
def post(self, request):
    serializer = EchoSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)   # 400 автоматически
    # ... работа с serializer.validated_data ...
    return Response({...}, status=200)
```

Запомните эту «тройку»: **создать → is_valid → validated_data**. В `ModelViewSet` она спрятана внутри `create()` / `update()`, но логика та же.

---

## Теория: APIView — что это и как живёт запрос

В Django есть function-based views и class-based views (CBV). **`APIView`** — CBV от DRF поверх Django.

### Зачем не обычный `django.views.View`

`APIView` добавляет:

1. Обёртку **`Request`** вместо сырого `HttpRequest` (удобные `.data`, `.query_params`, `.user` после auth).
2. Разбор тела JSON / form-data.
3. Проверку **authentication** и **permissions** до вашего `get`/`post`.
4. Единый **`Response`** + выбор рендера (JSON в curl, HTML-форма в браузере).
5. Обработчик исключений DRF (`ValidationError` → 400, `NotAuthenticated` → 401…).

### Имена методов = HTTP-методы

```python
class EchoView(APIView):
    def get(self, request):   ...   # GET
    def post(self, request):  ...   # POST
    def put(self, request):   ...   # PUT
    def patch(self, request): ...   # PATCH
    def delete(self, request): ...  # DELETE
```

Если клиент шлёт `POST`, а метода `post` нет — ответ **405 Method Not Allowed**.

### Порядок внутри `APIView.dispatch` (упрощённо)

```text
HTTP-запрос
  → as_view() создаёт экземпляр View
  → dispatch(request)
       → initialize_request   # HttpRequest → DRF Request
       → initial()
            → perform_authentication
            → check_permissions
            → check_throttles
       → get/post/put/...     # ваш код
       → finalize_response    # Response → HttpResponse
```

Пока permissions = `AllowAny` и auth не настроен — `request.user` будет `AnonymousUser`. На шаге 3 появится JWT, и `initial()` начнёт подставлять реального User.

### `request` в DRF ≠ `request` в Django

| Атрибут | Смысл |
|---------|--------|
| `request.data` | тело запроса (JSON/form) уже как dict — **для POST/PUT/PATCH** |
| `request.query_params` | query string (`?search=чай`) — аналог `request.GET` |
| `request.user` | User или AnonymousUser |
| `request.auth` | токен/учётные данные auth-бэкенда (или None) |
| `request.method` | `'GET'`, `'POST'`, … |

Не используйте `request.POST` в APIView для JSON — там пусто; нужен `request.data`.

### `Response` vs `JsonResponse`

```python
return Response({'status': 'ok'})           # DRF: сам выберет JSON или browsable HTML
return JsonResponse({'status': 'ok'})       # Django: всегда JSON, без browsable API
```

В DRF-проектах почти всегда `Response`.

### APIView vs ViewSet (задел на шаг 5)

| | `APIView` | `ViewSet` / `ModelViewSet` |
|---|-----------|----------------------------|
| Методы | `get`, `post`, … | `list`, `retrieve`, `create`, `update`, `destroy` |
| URL | только вручную `path(...)` | обычно `DefaultRouter` |
| Когда | login, health, confirm-email, «одна операция» | ресурс с полным CRUD (товары, промокоды) |

ViewSet **не** заменяет понимание APIView: внутри `create()` у ModelViewSet по сути тот же цикл «serializer → is_valid → save».

### Permissions и authentication (кратко; детали — шаг 3)

- **Authentication** — *кто* пришёл.
- **Permission** — *можно ли* этому кто.

Гость может `GET /products/`, но не `POST`. Настраивается классами permissions, не «магией ViewSet».

### Browsable API

Открыли endpoint в браузере — DRF рисует HTML с формой. Это **учебный** UI, не фронтенд магазина. Удобно отлаживать; с шага 7 основной инструмент — Swagger UI.

---

## 1. Подключить DRF в `settings.py`

В `INSTALLED_APPS` добавьте:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
]
```

Базовые настройки DRF (пока простые; JWT добавим на шаге 3):

```python
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}
```

**Разбор:**

- `AllowAny` — на этом шаге любой может дергать Hello API (потом сузим).
- Пагинация — списки товаров не будут отдавать 10 000 записей одним ответом.

---

## 2. Приложение `core` для служебных endpoint’ов

```bash
python manage.py startapp core
```

Добавьте `'core'` в `INSTALLED_APPS`.

---

## 3. Первый view: `core/views.py`

```python
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Проверка, что DRF подключён и отвечает JSON."""

    def get(self, request):
        return Response({
            'status': 'ok',
            'service': 'online-shop',
            'user': str(request.user),
        })
```

**Разбор построчно:**

- `APIView` — базовый класс DRF; у него уже разбор JSON body, content negotiation, exception handler.
- `get(self, request)` — обработчик HTTP GET. Имя метода = имя HTTP-метода в нижнем регистре.
- `request` здесь — **DRF Request**, обёртка над Django `HttpRequest`. У него есть `.user`, `.data`, `.query_params`.
- `Response({...})` — не `JsonResponse`. DRF сам выберет рендер (JSON в curl, HTML в браузере).
- `str(request.user)` для гостя даст `AnonymousUser` — так мы видим, что auth ещё не настроен.

---

## 4. URL: `core/urls.py` и корень

Создайте `core/urls.py`:

```python
from django.urls import path

from .views import HealthView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
]
```

В `config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

Итоговый URL: `GET /api/health/`.

**Склейка путей (см. теорию выше):**

```text
config/urls.py:   path('api/', include('core.urls'))
core/urls.py:     path('health/', HealthView.as_view())
                  path('echo/', EchoView.as_view())
→ /api/health/    → /api/echo/
```

`HealthView.as_view()` — обязательный вызов: Django вызывает **функцию**, а не класс. Внутри DRF эта функция создаст экземпляр `HealthView` и вызовет `dispatch` → `get`.

**Почему префикс `/api/`?**  
Отделяем JSON API от admin и будущих служебных страниц. Все ресурсы магазина будут жить под `/api/...`. На шаге 5 под тем же префиксом появится Router с `/api/products/` — тот же `include`, другой app.

---

## 5. Мини-пример Serializer (не обязателен для health, но нужен для понимания)

Добавьте в `core/serializers.py`:

```python
from rest_framework import serializers


class EchoSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class EchoView(APIView):
    pass  # см. ниже — лучше положить view в views.py
```

Лучше сразу в `core/views.py` добавить:

```python
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import EchoSerializer


class HealthView(APIView):
    def get(self, request):
        return Response({
            'status': 'ok',
            'service': 'online-shop',
            'user': str(request.user),
        })


class EchoView(APIView):
    """Демонстрация валидации входа через Serializer."""

    def post(self, request):
        serializer = EchoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(
            {'echo': serializer.validated_data['message']},
            status=status.HTTP_200_OK,
        )
```

`core/serializers.py`:

```python
from rest_framework import serializers


class EchoSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)
```

И в `core/urls.py`:

```python
from django.urls import path

from .views import EchoView, HealthView

urlpatterns = [
    path('health/', HealthView.as_view(), name='health'),
    path('echo/', EchoView.as_view(), name='echo'),
]
```

**Разбор `EchoView` (связь serializer + APIView + URL):**

1. URL `path('echo/', EchoView.as_view())` → только этот класс обслуживает `/api/echo/`.
2. Клиент шлёт **POST** → вызывается `post`, не `get`.
3. `request.data` — уже распарсенный JSON (`{'message': 'привет'}`), не `request.POST`.
4. `EchoSerializer(data=...)` — режим **десериализации** (вход). Без `data=` это был бы режим выхода.
5. `is_valid(raise_exception=True)` — при ошибке DRF сам отвечает **400** и телом `errors`; ваш код ниже не выполнится.
6. `validated_data` — очищенные данные; **не** берите поля из сырого `request.data` после валидации.
7. `Response({...})` — DRF превратит dict в JSON (curl) или HTML (браузер).

Это паттерн на весь курс: регистрация, корзина, заказ. На шаге 5 тот же цикл спрячется внутрь `ModelViewSet.create()`, но шаги те же.

**Сравнение с тем, что будет на шаге 5:**

| Сейчас (шаг 2) | Потом (шаг 5) |
|----------------|---------------|
| `Serializer` руками | `ModelSerializer` из модели |
| `APIView.post` | `ModelViewSet.create` |
| `path('echo/', …)` | `router.register('products', …)` |

---

## Теория: статус-коды, которые вы будете видеть часто

| Код | Когда |
|-----|--------|
| 200 | успешный GET/PATCH |
| 201 | ресурс создан (POST) |
| 204 | удалён, тела нет |
| 400 | ошибка валидации serializer |
| 401 | не аутентифицирован (нет/битый токен) |
| 403 | аутентифицирован, но роль не та (клиент лезет в CRUD товаров) |
| 404 | объект не найден |

---

## ✅ Ручная проверка

```bash
python manage.py runserver
```

```bash
curl -s http://127.0.0.1:8000/api/health/ | python -m json.tool
curl -s -X POST http://127.0.0.1:8000/api/echo/ \
  -H 'Content-Type: application/json' \
  -d '{"message":"hello shop"}' | python -m json.tool
curl -s -o /tmp/echo_err.json -w '%{http_code}\n' -X POST http://127.0.0.1:8000/api/echo/ \
  -H 'Content-Type: application/json' \
  -d '{}'
cat /tmp/echo_err.json
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `GET /api/health/` | `{"status":"ok",...}` |
| ☐ | Браузер: `/api/health/` | browsable API HTML |
| ☐ | `POST /api/echo/` с message | `{"echo":"hello shop"}` |
| ☐ | `POST /api/echo/` пустой body | HTTP 400, ошибка по полю `message` |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Health endpoint | `tests/test_core_api.py` | GET → 200, `status=ok` |
| Echo OK | там же | POST с `message` → 200 и echo |
| Echo валидация | там же | POST без `message` → 400 |
| EchoSerializer unit | `tests/test_core_serializers.py` | `is_valid` True/False без HTTP |

```python
# tests/test_core_api.py
import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api():
    return APIClient()


@pytest.mark.django_db
def test_health_ok(api):
    r = api.get('/api/health/')
    assert r.status_code == 200
    assert r.data['status'] == 'ok'


@pytest.mark.django_db
def test_echo_ok(api):
    r = api.post('/api/echo/', {'message': 'hello'}, format='json')
    assert r.status_code == 200
    assert r.data['echo'] == 'hello'


@pytest.mark.django_db
def test_echo_requires_message(api):
    r = api.post('/api/echo/', {}, format='json')
    assert r.status_code == 400
    assert 'message' in r.data
```

```python
# tests/test_core_serializers.py
from core.serializers import EchoSerializer


def test_echo_serializer_valid():
    s = EchoSerializer(data={'message': 'x'})
    assert s.is_valid(), s.errors


def test_echo_serializer_empty_invalid():
    s = EchoSerializer(data={})
    assert not s.is_valid()
    assert 'message' in s.errors
```

```bash
pytest tests/test_core_api.py tests/test_core_serializers.py
```

**Все пункты отмечены?** → [step-03-users-roles.md](step-03-users-roles.md)

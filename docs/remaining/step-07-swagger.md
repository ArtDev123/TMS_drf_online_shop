# Шаг 7 — Swagger / OpenAPI (вместо Postman)

**Предыдущий:** [step-06-catalog-public.md](step-06-catalog-public.md) · **Следующий:** [step-08-registration-email.md](step-08-registration-email.md)

## Задача

Подключить интерактивную документацию API: **Swagger UI** и схема OpenAPI. Дальше можно дергать эндпоинты из браузера — с JWT Authorize — без Postman/Insomnia.

К этому моменту уже есть публичный каталог и защищённый CRUD менеджера — в Swagger сразу видно оба режима доступа.

Используем **`drf-spectacular`** (актуальный генератор схемы для DRF). Альтернатива `drf-yasg` устаревает.

```text
ViewSet / Serializer  →  OpenAPI schema (JSON/YAML)
                              ↓
                    Swagger UI  /  ReDoc
                    (Try it out + Authorize)
```

---

## Теория: зачем OpenAPI, а не только browsable API

| Инструмент | Плюсы | Минусы |
|------------|--------|--------|
| Browsable API DRF (`/api/products/`) | уже есть | неудобно для JWT, нет единого каталога методов |
| Postman / Insomnia | коллекции, окружения | вручную синхронизировать с кодом |
| **Swagger UI** | схема из кода, Try it out, Authorize | нужен пакет + настройки |

Схема обновляется сама, когда вы меняете serializers/ViewSets — это главная выгода для учебного проекта.

---

## 1. Установить пакет

```bash
pip install drf-spectacular
```

Добавьте в `requirements.txt`:

```text
drf-spectacular
```

---

## 2. Settings — `config/settings.py`

В `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    # ... ваши apps
]
```

В `REST_FRAMEWORK` добавьте класс схемы:

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
```

Метаданные API (заголовок Swagger, описание JWT):

```python
SPECTACULAR_SETTINGS = {
    'TITLE': 'Online Shop API',
    'DESCRIPTION': 'Учебный магазин на Django REST Framework',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # JWT в кнопке Authorize → значение: Bearer <access>
    'COMPONENT_SPLIT_REQUEST': True,
}
```

`drf-spectacular` по JWT обычно подхватывает `JWTAuthentication` и рисует scheme `jwtAuth` / Bearer. Если в UI нет Authorize — добавьте явно:

```python
SPECTACULAR_SETTINGS = {
    # ... как выше
    'SECURITY': [{'jwtAuth': []}],
    'APPEND_COMPONENTS': {
        'securitySchemes': {
            'jwtAuth': {
                'type': 'http',
                'scheme': 'bearer',
                'bearerFormat': 'JWT',
            }
        }
    },
}
```

---

## 3. URL — `config/urls.py`

```python
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import EmailTokenObtainPairView

urlpatterns = [
    path('admin/', admin.site.urls),

    # OpenAPI / Swagger
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(url_name='schema'),
        name='swagger-ui',
    ),
    path(
        'api/redoc/',
        SpectacularRedocView.as_view(url_name='schema'),
        name='redoc',
    ),

    path('api/health/', include('core.urls')),
    path('api/auth/token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/', include('catalog.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

| URL | Что открыть |
|-----|-------------|
| [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/) | **Swagger UI** — основной рабочий инструмент |
| [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/) | ReDoc — читаемая документация |
| [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/) | сырая OpenAPI-схема (JSON) |

---

## 4. Как пользоваться вместо Postman

### Гость (без токена)

1. Откройте `/api/docs/`.
2. Найдите `GET /api/products/` → **Try it out** → **Execute**.
3. Должен быть **200** и список активных товаров (шаг 6).

### Менеджер (JWT)

1. В Swagger найдите `POST /api/auth/token/` (или ваш obtain endpoint).
2. Body:

```json
{
  "email": "manager@shop.local",
  "password": "manager123"
}
```

3. Скопируйте `access` из ответа.
4. Нажмите **Authorize** (замок вверху справа).
5. Вставьте токен:
   - если поле ждёт raw token — только `eyJ...`;
   - если scheme Bearer уже выбран — тоже обычно только `eyJ...` (префикс `Bearer` добавит UI).
6. **Authorize** → **Close**.
7. Теперь `POST /api/products/` / `POST /api/categories/` уходят с заголовком `Authorization: Bearer …`.

Проверка: без Authorize `POST /api/products/` → **401**; с токеном менеджера → **201**.

### Типичные ошибки

| Симптом | Что проверить |
|---------|----------------|
| Authorize есть, но всё равно 401 | не тот токен / истек access / забыли нажать Authorize |
| 403 на POST | вошли клиентом, а нужен менеджер |
| Эндпоинта нет в Swagger | view не в `urlpatterns` / не зарегистрирован в Router |
| Схема пустая / 500 на `/api/schema/` | ошибка в serializer/`@extend_schema` — смотрите traceback runserver |

---

## 5. (Опционально) подписи к эндпоинтам

Чтобы в Swagger были человеческие описания:

```python
from drf_spectacular.utils import extend_schema, extend_schema_view

from rest_framework import viewsets


@extend_schema_view(
    list=extend_schema(summary='Список товаров', tags=['catalog']),
    create=extend_schema(summary='Создать товар (менеджер)', tags=['catalog']),
    retrieve=extend_schema(summary='Карточка товара', tags=['catalog']),
)
class ProductViewSet(viewsets.ModelViewSet):
    ...
```

На минималках можно не трогать — auto-schema и так покажет модели и поля.

Для кастомного JWT-view (email вместо username) иногда нужно явно описать request body — если Swagger рисует `username`, добавьте:

```python
from drf_spectacular.utils import extend_schema
from rest_framework_simplejwt.views import TokenObtainPairView


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer  # как на шаге 3

    @extend_schema(
        summary='Получить JWT по email',
        tags=['auth'],
    )
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)
```

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `pip install drf-spectacular` + restart runserver | без ошибок импорта |
| ☐ | Открыть `/api/docs/` | UI со списком эндпоинтов |
| ☐ | GET `/api/products/` из Swagger без токена | 200 |
| ☐ | POST `/api/auth/token/` → Authorize | замок «авторизован» |
| ☐ | POST `/api/categories/` или `/api/products/` менеджером | 201 |
| ☐ | Открыть `/api/redoc/` | читаемая документация |

Дальше в гайде вместо длинных `curl` можно проверять шаги через **Try it out**.

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Схема отдаётся | `tests/test_schema.py` | GET `/api/schema/` → 200 |
| Swagger UI | там же | GET `/api/docs/` → 200 |

```python
# tests/test_schema.py
import pytest


@pytest.mark.django_db
def test_openapi_schema(api):
    r = api.get('/api/schema/')
    assert r.status_code == 200
    assert 'openapi' in r.data or 'openapi' in r.content.decode().lower()


@pytest.mark.django_db
def test_swagger_ui(api):
    r = api.get('/api/docs/')
    assert r.status_code == 200
```

```bash
pytest tests/test_schema.py
```

**Все пункты отмечены?** → [step-08-registration-email.md](step-08-registration-email.md)

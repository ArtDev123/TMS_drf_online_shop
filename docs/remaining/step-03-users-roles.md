# Шаг 3 — Пользователи, роли, JWT, permissions

**Предыдущий:** [step-02-drf-basics.md](step-02-drf-basics.md) · **Следующий:** [step-04-products-models.md](step-04-products-models.md)

## Задача

Закрыть требование ТЗ «3 типа пользователей»: гость, клиент, менеджер. Сделать кастомную модель пользователя (имя, фамилия, email, телефон), выдачу JWT и permission-классы `IsManager` / `IsClient`.

---

## Теория: Authentication vs Permission

```text
Запрос с заголовком Authorization: Bearer <access>
        │
        ▼
Authentication  →  request.user = User(...)  или AnonymousUser
        │
        ▼
Permission      →  True / False  →  403 если False
        │
        ▼
ViewSet.create / list / ...   (или APIView.get / post)
```

Это встраивается в уже знакомый цикл `APIView` / ViewSet из шага 2:

```text
dispatch → initial()
              → perform_authentication   # JWT читает заголовок
              → check_permissions        # IsManager / IsAuthenticated / …
         → ваш get/post/list/create
```

Частая ошибка новичков: поставить глобально `IsAuthenticated` и думать, что гость «отсечён от всего».  
В каталоге гостю **нужен** `AllowAny` на чтение, а на запись — только менеджер. Это делается через `get_permissions()` у ViewSet (шаг 5–6), а не одним классом на весь проект.

### Где задавать

| Уровень | Пример | Эффект |
|---------|--------|--------|
| `settings.REST_FRAMEWORK['DEFAULT_…']` | дефолт на все APIView/ViewSet | удобный baseline |
| `permission_classes` / `authentication_classes` на классе | переопределение для одного view | чаще всего так |
| `get_permissions()` | разный список по `self.action` | каталог: GET всем, POST менеджеру |

Позже `IsManager` повесим на `ProductViewSet`; на `HealthView` можно оставить доступ открытым через `permission_classes = [AllowAny]` или не трогать, если дефолт ещё мягкий.

---

## Теория: почему кастомный User с самого начала

ТЗ фиксирует поля клиента: имя, фамилия, email, телефон. Стандартный `auth.User` имеет `username` и не имеет `phone`. Менять User после первых миграций больно — поэтому `AUTH_USER_MODEL` задаём **до** бизнес-моделей с FK на User.

Email сделаем уникальным логином: для магазина это естественнее username.

---

## 1. Приложение `accounts`

```bash
python manage.py startapp accounts
```

В `INSTALLED_APPS` — `'accounts'` **выше** приложений, которые будут ссылаться на User (пока их нет — всё равно добавьте сразу).

---

## 2. Модель пользователя — `accounts/models.py`

```python
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserRole(models.TextChoices):
    CLIENT = 'CLIENT', 'Клиент'
    MANAGER = 'MANAGER', 'Менеджер магазина'


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('Email обязателен')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        extra_fields.setdefault('role', UserRole.CLIENT)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.MANAGER)
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True')
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # логинимся по email
    email = models.EmailField('email', unique=True)
    phone = models.CharField(max_length=32, blank=True)
    role = models.CharField(
        max_length=16,
        choices=UserRole.choices,
        default=UserRole.CLIENT,
    )
    email_confirmed = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name']

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def is_manager(self):
        return self.role == UserRole.MANAGER or self.is_superuser

    @property
    def is_client(self):
        return self.role == UserRole.CLIENT
```

**Разбор:**

| Поле / кусок | Зачем |
|--------------|--------|
| `username = None` | убираем обязательный username из AbstractUser |
| `USERNAME_FIELD = 'email'` | `authenticate` и JWT ищут пользователя по email |
| `role` | явное различие клиент / менеджер без путаницы с `is_staff` |
| `email_confirmed` | для шага 8: пока False — можно запретить заказ |
| `is_manager` / `is_client` | удобные свойства для permissions |
| `UserManager.create_superuser` | `createsuperuser` спросит email, не username |

Поля `first_name`, `last_name` уже есть в `AbstractUser` — отдельно не дублируем.

---

## 3. Settings: `AUTH_USER_MODEL` + JWT

В `config/settings.py`:

```python
AUTH_USER_MODEL = 'accounts.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',  # удобно для browsable API / admin
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

from datetime import timedelta

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
}
```

**Важно:** если вы уже успели сделать `migrate` на шаге 1 со стандартным User — для учебного проекта проще удалить БД и накатить заново:

```bash
sudo -u postgres psql -c "DROP DATABASE shop_db;"
sudo -u postgres psql -c "CREATE DATABASE shop_db OWNER shop_user;"
python manage.py makemigrations accounts
python manage.py migrate
python manage.py createsuperuser
```

---

## 4. Admin — `accounts/admin.py`

```python
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'first_name', 'last_name', 'role', 'email_confirmed', 'is_staff')
    list_filter = ('role', 'email_confirmed', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone')

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Личные данные', {'fields': ('first_name', 'last_name', 'phone')}),
        ('Роль', {'fields': ('role', 'email_confirmed')}),
        ('Права', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'phone', 'role', 'password1', 'password2'),
        }),
    )
```

---

## 5. Permissions — `accounts/permissions.py`

```python
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import UserRole


class IsManager(BasePermission):
    """Только менеджер магазина (или суперпользователь)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_manager)


class IsClient(BasePermission):
    """Только клиент с подтверждённым email (для заказа/корзины можно усилить)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == UserRole.CLIENT
        )


class IsClientOrReadOnly(BasePermission):
    """Пример комбинированного правила (пригодится позже)."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)
```

**Разбор `BasePermission`:**

- `has_permission(request, view)` — доступ к endpoint в целом (список/создание).
- `has_object_permission(request, view, obj)` — доступ к конкретному объекту (чужая корзина — нельзя).
- `SAFE_METHODS` = `GET`, `HEAD`, `OPTIONS` — «только чтение».

`IsClient` пока **не** требует `email_confirmed` — включим на шаге 8, чтобы не ломать проверки раньше времени. Можно завести отдельно `IsConfirmedClient`.

---

## 6. URL для JWT

В `config/urls.py`:

```python
from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/health/', include('core.urls')),  # или path('api/', include(...)) как было
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

Если на шаге 2 у вас было `path('api/', include('core.urls'))` — оставьте так и **добавьте** JWT-пути рядом, не ломая health/echo:

```python
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('core.urls')),
    path('api/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
```

SimpleJWT по умолчанию ждёт поле `username` в JSON. Мы логинимся по email — нужен кастомный serializer.

Создайте `accounts/serializers.py`:

```python
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


User = get_user_model()


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    username_field = User.EMAIL_FIELD  # 'email'

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['role'] = user.role
        token['email'] = user.email
        return token
```

`accounts/views.py`:

```python
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import EmailTokenObtainPairSerializer


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer
```

В `config/urls.py` замените `TokenObtainPairView` на:

```python
from accounts.views import EmailTokenObtainPairView

path('api/auth/token/', EmailTokenObtainPairView.as_view(), name='token_obtain_pair'),
```

Тело запроса:

```json
{"email": "manager@shop.local", "password": "..."}
```

---

## 7. Создать менеджера

В admin или shell:

```bash
python manage.py shell -c "
from accounts.models import User, UserRole
u, created = User.objects.get_or_create(
    email='manager@shop.local',
    defaults={
        'first_name': 'Shop',
        'last_name': 'Manager',
        'phone': '+10000000000',
        'role': UserRole.MANAGER,
        'email_confirmed': True,
        'is_staff': True,
    },
)
if created:
    u.set_password('manager123')
    u.save()
print(u.email, u.role, 'created=', created)
"
```

---

## Теория: как клиент ходит с JWT

1. `POST /api/auth/token/` → `{ "access": "...", "refresh": "..." }`
2. Каждый защищённый запрос:

```http
Authorization: Bearer <access>
```

3. Когда access истёк — `POST /api/auth/token/refresh/` с `{"refresh":"..."}`.

Гость **не** получает токен и остаётся `AnonymousUser`.

---

## ✅ Ручная проверка

```bash
python manage.py makemigrations accounts
python manage.py migrate
python manage.py runserver
```

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"email":"manager@shop.local","password":"manager123"}' | python -m json.tool
```

Сохраните `access` в переменную и проверьте health (пока AllowAny на HealthView — либо временно):

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | migrate accounts | таблицы User без ошибок |
| ☐ | Admin → Users | видны email, role, phone |
| ☐ | POST token с верным паролем | `access` + `refresh` |
| ☐ | POST token с неверным паролем | 401 |
| ☐ | Shell: `User.objects.get(...).is_manager` | `True` для менеджера |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Создание User по email | `tests/test_accounts_models.py` | `USERNAME_FIELD`, `is_manager` |
| JWT получить | `tests/test_auth_jwt.py` | верный пароль → `access`+`refresh` |
| JWT отказ | там же | неверный пароль → 401 |
| IsManager permission | `tests/test_permissions.py` | менеджер True, клиент False |

```python
# tests/conftest.py  (общие фикстуры — пригодятся дальше)
import pytest
from accounts.models import User, UserRole


@pytest.fixture
def manager(db):
    return User.objects.create_user(
        email='manager@test.local',
        password='pass12345',
        first_name='M',
        last_name='G',
        role=UserRole.MANAGER,
        email_confirmed=True,
    )


@pytest.fixture
def client_user(db):
    return User.objects.create_user(
        email='client@test.local',
        password='pass12345',
        first_name='C',
        last_name='L',
        role=UserRole.CLIENT,
        email_confirmed=True,
    )
```

```python
# tests/test_auth_jwt.py
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_token_ok(manager):
    api = APIClient()
    r = api.post('/api/auth/token/', {
        'email': manager.email,
        'password': 'pass12345',
    }, format='json')
    assert r.status_code == 200
    assert 'access' in r.data and 'refresh' in r.data


@pytest.mark.django_db
def test_token_bad_password(manager):
    api = APIClient()
    r = api.post('/api/auth/token/', {
        'email': manager.email,
        'password': 'wrong',
    }, format='json')
    assert r.status_code == 401
```

```python
# tests/test_permissions.py
import pytest
from rest_framework.test import APIRequestFactory
from accounts.permissions import IsManager


@pytest.mark.django_db
def test_is_manager_permission(manager, client_user):
    factory = APIRequestFactory()
    perm = IsManager()
    req_m = factory.get('/')
    req_m.user = manager
    req_c = factory.get('/')
    req_c.user = client_user
    assert perm.has_permission(req_m, None) is True
    assert perm.has_permission(req_c, None) is False
```

```bash
pytest tests/test_auth_jwt.py tests/test_permissions.py tests/test_accounts_models.py -q
```

**Все пункты отмечены?** → [step-04-products-models.md](step-04-products-models.md)

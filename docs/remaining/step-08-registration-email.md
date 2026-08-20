# Шаг 8 — Регистрация клиента с подтверждением email

**Предыдущий:** [step-07-swagger.md](step-07-swagger.md) · **Следующий:** [step-09-cart.md](step-09-cart.md)

## Задача

Доп. функционал ТЗ: клиент регистрируется и **подтверждает email**. Пока email не подтверждён — `email_confirmed=False`; заказ и корзину можно разрешить только подтверждённым (настроим permission).

---

## Теория: поток подтверждения

```text
POST /api/auth/register/
   → создаём User (email_confirmed=False)
   → генерируем токен (uid + token) как в Django PasswordReset
   → шлём письмо со ссылкой / кодом

GET или POST /api/auth/confirm-email/?uid=..&token=..
   → проверяем токен
   → email_confirmed=True
```

В учебном проекте письма пишем в **консоль** (`EMAIL_BACKEND = console`) — не нужен реальный SMTP.

---

## 1. Настройки email в `settings.py`

```python
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = 'shop@localhost'
FRONTEND_CONFIRM_URL = 'http://127.0.0.1:8000/api/auth/confirm-email/'
```

Позже для продакшена замените backend на SMTP и URL — на адрес фронтенда.

---

## 2. Сериализатор регистрации — `accounts/serializers.py`

Добавьте (рядом с JWT-сериализатором):

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import serializers

from .models import UserRole

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = (
            'email',
            'password',
            'password_confirm',
            'first_name',
            'last_name',
            'phone',
        )

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Пароли не совпадают'})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(
            role=UserRole.CLIENT,
            email_confirmed=False,
            **validated_data,
        )
        user.set_password(password)
        user.save()
        return user


class ConfirmEmailSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
```

**Разбор:**

- `write_only=True` у пароля — никогда не вернётся в JSON-ответе.
- `create` не сохраняет сырой пароль: только `set_password` (хеш).
- Роль жёстко `CLIENT` — зарегистрироваться менеджером через публичный API нельзя.

---

## 3. Письмо — `accounts/services.py`

```python
from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .utils import email_token_generator


def send_confirmation_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_token_generator.make_token(user)
    # Не вставляем полную ссылку с "?uid=...&token=...":
    # console backend + quoted-printable превращает "=" в "=3D".
    send_mail(
        subject='Verify email: Online Shop',
        message=(
            f'Hello {user.first_name}!\n\n'
            f'Confirm URL: {settings.FRONTEND_CONFIRM_URL}\n'
            f'uid: {uid}\n'
            f'token: {token}\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return uid, token  # token возвращаем только для тестов/шелла, в проде не логировать
```

В письме — отдельно `uid` и `token`. Подтверждение через POST (как ниже) или GET, собрав query сами. Нормальный SMTP-клиент QP декодирует сам; ломается именно копирование из console backend.

`email_token_generator` / `default_token_generator` — токен привязан к user + хешу пароля + timestamp, одноразово «портится» после смены пароля.

---

## 4. Views — дописать `accounts/views.py`

```python
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ConfirmEmailSerializer,
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
)
from .services import send_confirmation_email

User = get_user_model()


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        send_confirmation_email(user)


def confirm_user_email(uid: str, token: str) -> tuple[bool, str]:
    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        return False, 'Некорректная ссылка'
    if not default_token_generator.check_token(user, token):
        return False, 'Токен недействителен'
    user.email_confirmed = True
    user.save(update_fields=['email_confirmed'])
    return True, 'Email подтверждён'


class ConfirmEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = ConfirmEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ok, msg = confirm_user_email(ser.validated_data['uid'], ser.validated_data['token'])
        return Response({'detail': msg}, status=200 if ok else 400)

    def get(self, request):
        ok, msg = confirm_user_email(
            request.query_params.get('uid', ''),
            request.query_params.get('token', ''),
        )
        return Response({'detail': msg}, status=200 if ok else 400)
```

Положите `confirm_user_email` в `accounts/services.py`.

---

## 5. URL

`accounts/urls.py`:

```python
from django.urls import path

from .views import ConfirmEmailView, EmailTokenObtainPairView, RegisterView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('auth/register/', RegisterView.as_view()),
    path('auth/confirm-email/', ConfirmEmailView.as_view()),
    path('auth/token/', EmailTokenObtainPairView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
]
```

В `config/urls.py` замените отдельные JWT-пути на:

```python
path('api/', include('accounts.urls')),
```

---

## 6. Permission «только подтверждённый клиент»

В `accounts/permissions.py`:

```python
class IsConfirmedClient(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_client
            and user.email_confirmed
        )
```

На шаге 9 повесьте его на корзину и на шаг 13 — на заказ.

---

## ✅ Ручная проверка

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/register/ \
  -H 'Content-Type: application/json' \
  -d '{
    "email":"client@shop.local",
    "password":"client12345",
    "password_confirm":"client12345",
    "first_name":"Ivan",
    "last_name":"Petrov",
    "phone":"+79991234567"
  }' | python -m json.tool
```

В терминале `runserver` появится текст письма с `uid` и `token`. Скопируйте и подтвердите:

```bash
curl -s -X POST http://127.0.0.1:8000/api/auth/confirm-email/ \
  -H 'Content-Type: application/json' \
  -d '{"uid":"…","token":"…"}' | python -m json.tool
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | POST register | 201, пользовательль в БД |
| ☐ | В консоли сервера | письмо со ссылкой |
| ☐ | `email_confirmed` до confirm | `False` |
| ☐ | POST confirm | `Email подтверждён`, флаг `True` |
| ☐ | Повторный register тем же email | 400 unique |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Регистрация | `tests/test_registration.py` | 201, `email_confirmed=False`, роль CLIENT |
| Письмо ушло | там же | `mail.outbox` длина 1 (locmem backend) |
| Confirm | там же | после confirm флаг `True` |
| Дубликат email | там же | 400 |
| Пароли не совпали | там же | 400 |

В тестах удобнее не console, а:

```python
# tests/conftest.py или pytest.ini через settings override
@pytest.fixture(autouse=True)
def email_backend(settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

```python
# tests/test_registration.py
import pytest
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from accounts.models import User, UserRole


@pytest.mark.django_db
def test_register_and_confirm(api):
    r = api.post('/api/auth/register/', {
        'email': 'new@test.local',
        'password': 'client12345',
        'password_confirm': 'client12345',
        'first_name': 'Ivan',
        'last_name': 'Petrov',
        'phone': '+7999',
    }, format='json')
    assert r.status_code == 201
    user = User.objects.get(email='new@test.local')
    assert user.role == UserRole.CLIENT
    assert user.email_confirmed is False
    assert len(mail.outbox) == 1

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    r = api.post('/api/auth/confirm-email/', {'uid': uid, 'token': token}, format='json')
    assert r.status_code == 200
    user.refresh_from_db()
    assert user.email_confirmed is True


@pytest.mark.django_db
def test_register_password_mismatch(api):
    r = api.post('/api/auth/register/', {
        'email': 'x@test.local',
        'password': 'client12345',
        'password_confirm': 'other',
        'first_name': 'A',
        'last_name': 'B',
        'phone': '',
    }, format='json')
    assert r.status_code == 400
```

```bash
pytest tests/test_registration.py
```

**Все пункты отмечены?** → [step-09-cart.md](step-09-cart.md)

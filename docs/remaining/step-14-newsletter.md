# Шаг 14 — Подписка на рассылку скидок (раз в неделю)

**Предыдущий:** [step-13-orders.md](step-13-orders.md) · **Следующий:** [step-15-cashback.md](step-15-cashback.md)

## Задача

Клиент подписывается на email-рассылку и **раз в неделю** получает письмо об актуальных скидках на товары (`ProductDiscount`, которые сейчас активны).

Фоновый запуск — Celery Beat (детали инфраструктуры — шаг 16). Здесь: модель подписки, API, задача «собрать скидки и разослать».

---

## Теория: зачем Celery, а не cron в view

HTTP-запрос не должен «раз в неделю сам себя будить». Нужен отдельный процесс:

```text
Celery Beat (планировщик)  →  раз в неделю кладёт задачу в Redis
Celery Worker              →  забирает задачу, шлёт письма
```

Пока Redis/Celery не подняты, задачу можно вызвать вручную:

```bash
python manage.py shell -c "from promotions.tasks import send_weekly_discounts; send_weekly_discounts()"
```

На шаге 16 обернём в `@shared_task` и расписание.

---

## 1. Модель подписки — `promotions/models.py`

Добавьте:

```python
class NewsletterSubscription(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='newsletter',
    )
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} active={self.is_active}'
```

Нужен импорт:

```python
from django.conf import settings
```

```bash
python manage.py makemigrations promotions
python manage.py migrate
```

---

## 2. API подписки / отписки

`promotions/serializers.py`:

```python
class NewsletterSerializer(serializers.ModelSerializer):
    class Meta:
        model = NewsletterSubscription
        fields = ('is_active', 'subscribed_at')
        read_only_fields = ('subscribed_at',)
```

`promotions/views.py`:

```python
from rest_framework.views import APIView
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from .models import NewsletterSubscription
from .serializers import NewsletterSerializer


class NewsletterView(APIView):
    permission_classes = [IsConfirmedClient]

    def get(self, request):
        sub, _ = NewsletterSubscription.objects.get_or_create(user=request.user)
        return Response(NewsletterSerializer(sub).data)

    def post(self, request):
        """Подписаться (или реактивировать)."""
        sub, _ = NewsletterSubscription.objects.get_or_create(user=request.user)
        sub.is_active = True
        sub.save(update_fields=['is_active'])
        return Response(NewsletterSerializer(sub).data)

    def delete(self, request):
        """Отписаться."""
        sub, _ = NewsletterSubscription.objects.get_or_create(user=request.user)
        sub.is_active = False
        sub.save(update_fields=['is_active'])
        return Response(NewsletterSerializer(sub).data)
```

URL: `path('newsletter/', NewsletterView.as_view())`.

---

## 3. Сбор актуальных скидок — `promotions/services/newsletter.py`

```python
from django.core.mail import send_mail
from django.conf import settings

from catalog.models import ProductDiscount
from promotions.models import NewsletterSubscription


def collect_active_discount_lines():
    lines = []
    for d in ProductDiscount.objects.select_related('product').filter(is_active=True):
        if d.is_currently_active() and d.product.is_active:
            lines.append(
                f'- {d.product.name}: {d.value} '
                f'{"%" if d.discount_type == "PERCENT" else "фикс."} '
                f'(было {d.product.price})'
            )
    return lines


def send_weekly_discounts():
    lines = collect_active_discount_lines()
    if not lines:
        body_discounts = 'На этой неделе активных скидок нет.'
    else:
        body_discounts = 'Актуальные скидки:\n' + '\n'.join(lines)

    recipients = list(
        NewsletterSubscription.objects.filter(is_active=True)
        .select_related('user')
        .values_list('user__email', flat=True)
    )
    for email in recipients:
        send_mail(
            subject='Еженедельные скидки — Online Shop',
            message=body_discounts,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
    return {'sent': len(recipients), 'discounts': len(lines)}
```

---

## 4. Management-команда для ручного запуска

`promotions/management/commands/send_weekly_discounts.py`:

```python
from django.core.management.base import BaseCommand

from promotions.services.newsletter import send_weekly_discounts


class Command(BaseCommand):
    help = 'Разовая рассылка актуальных скидок подписчикам'

    def handle(self, *args, **options):
        result = send_weekly_discounts()
        self.stdout.write(self.style.SUCCESS(str(result)))
```

Не забудьте пустые `__init__.py` в `management/` и `management/commands/`.

```bash
python manage.py send_weekly_discounts
```

Письма появятся в консоли runserver / shell (console email backend).

---

## 5. Связь с Celery (заготовка)

`promotions/tasks.py`:

```python
from celery import shared_task

from promotions.services.newsletter import send_weekly_discounts as _send


@shared_task
def send_weekly_discounts_task():
    return _send()
```

Пока Celery не настроен, импорт `shared_task` упадёт — либо установите celery (шаг 1 requirements), либо временно закомментируйте декоратор и оставьте обычную функцию. На шаге 16 подключим Beat: `crontab(day_of_week='mon', hour=10, minute=0)`.

---

## ✅ Ручная проверка

```bash
curl -s -X POST http://127.0.0.1:8000/api/newsletter/ \
  -H "Authorization: Bearer $CTOKEN" | python -m json.tool

python manage.py send_weekly_discounts
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | POST newsletter | `is_active: true` |
| ☐ | DELETE newsletter | `is_active: false` |
| ☐ | Есть активная ProductDiscount | письмо со списком в консоли |
| ☐ | Нет подписчиков | `sent: 0` |
| ☐ | Гость POST | 401 |

---

## 🧪 Покрытие тестами

| Что | Файл | Проверка |
|-----|------|----------|
| Подписка / отписка | `tests/test_newsletter.py` | POST `is_active=True`, DELETE `False` |
| `collect_active_discount_lines` | там же | только активные скидки |
| `send_weekly_discounts` | там же | письмо в `mail.outbox` подписчику |
| Неактивный подписчик | там же | письмо не уходит |
| Гость | там же | 401 |

```python
# tests/test_newsletter.py
from decimal import Decimal
import pytest
from django.core import mail
from catalog.models import Category, Product, ProductDiscount, DiscountType
from promotions.models import NewsletterSubscription
from promotions.services.newsletter import send_weekly_discounts


@pytest.mark.django_db
def test_subscribe_unsubscribe(client_api, client_user):
    r = client_api.post('/api/newsletter/')
    assert r.status_code == 200
    assert r.data['is_active'] is True
    r = client_api.delete('/api/newsletter/')
    assert r.data['is_active'] is False


@pytest.mark.django_db
def test_weekly_send_only_active_subscribers(client_user, settings):
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
    NewsletterSubscription.objects.create(user=client_user, is_active=True)
    p = Product.objects.create(
        category=Category.objects.create(name='C', slug='c-nl'),
        name='P', slug='nl', price=Decimal('100'), stock=1, is_active=True,
    )
    ProductDiscount.objects.create(
        product=p, discount_type=DiscountType.PERCENT, value=Decimal('15'), is_active=True,
    )
    result = send_weekly_discounts()
    assert result['sent'] == 1
    assert len(mail.outbox) == 1
    assert 'P' in mail.outbox[0].body
```

```bash
pytest tests/test_newsletter.py
```

**Все пункты отмечены?** → [step-15-cashback.md](step-15-cashback.md)

# Шаг 16 — Celery, Redis, почта: сводка фоновых задач

**Предыдущий:** [step-15-cashback.md](step-15-cashback.md) · **Следующий:** [step-17-final.md](step-17-final.md)

## Задача

Свести воедино всё, что уходит «не в HTTP-запросе»:

1. Еженедельная рассылка скидок.
2. Напоминание о доставке за 1 день / 6 ч / 1 ч.

Поднять Redis + Celery Worker + Celery Beat (или django-celery-beat).

---

## Теория: роли процессов

| Процесс | Роль |
|---------|------|
| `runserver` / gunicorn | HTTP API |
| `redis-server` | брокер очередей |
| `celery worker` | выполняет задачи |
| `celery beat` | по расписанию кладёт задачи в очередь |

Без worker письмо «запланируется», но не отправится.

---

## 1. Redis

```bash
# Ubuntu/Debian пример
sudo apt install redis-server
redis-cli ping   # PONG
```

---

## 2. Celery в Django — `config/celery.py`

```python
import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
```

`config/__init__.py`:

```python
from .celery import app as celery_app

__all__ = ('celery_app',)
```

`settings.py`:

```python
CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://127.0.0.1:6379/1')
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'weekly-discounts': {
        'task': 'promotions.tasks.send_weekly_discounts_task',
        'schedule': 60 * 60 * 24 * 7,  # секунды; лучше crontab — ниже
    },
}
```

Лучше через crontab:

```python
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    'weekly-discounts': {
        'task': 'promotions.tasks.send_weekly_discounts_task',
        'schedule': crontab(day_of_week='monday', hour=10, minute=0),
    },
}
```

Добавьте в `.env`:

```text
CELERY_BROKER_URL=redis://127.0.0.1:6379/0
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/1
```

---

## 3. Задача напоминания о доставке

`orders/tasks.py`:

```python
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


@shared_task
def send_delivery_reminder(order_id: int):
    from orders.models import Order

    try:
        order = Order.objects.select_related('user').get(pk=order_id)
    except Order.DoesNotExist:
        return {'ok': False, 'reason': 'missing'}

    if order.delivery_notified:
        return {'ok': False, 'reason': 'already'}

    send_mail(
        subject=f'Напоминание о доставке заказа #{order.id}',
        message=(
            f'Здравствуйте, {order.user.first_name}!\n\n'
            f'Ваш заказ #{order.id} будет доставлен примерно в '
            f'{order.delivery_at.astimezone().strftime("%d.%m.%Y %H:%M")}.\n'
            f'Сумма: {order.total}.\n'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[order.user.email],
        fail_silently=False,
    )
    order.delivery_notified = True
    order.save(update_fields=['delivery_notified'])
    return {'ok': True, 'order_id': order_id}


def schedule_delivery_notification(order_id: int, notify_at):
    """Заменить заглушку шага 13."""
    if notify_at <= timezone.now():
        send_delivery_reminder.delay(order_id)
    else:
        send_delivery_reminder.apply_async(args=[order_id], eta=notify_at)
```

В `orders/services.py` импорт уже ожидает `schedule_delivery_notification` из `orders.tasks` — заглушка заменяется этим файлом.

---

## 4. Задача рассылки

`promotions/tasks.py` (как на шаге 14, финально):

```python
from celery import shared_task

from promotions.services.newsletter import send_weekly_discounts


@shared_task(name='promotions.tasks.send_weekly_discounts_task')
def send_weekly_discounts_task():
    return send_weekly_discounts()
```

---

## 5. Запуск трёх терминалов

```bash
# терминал 1
source .venv/bin/activate
python manage.py runserver

# терминал 2
source .venv/bin/activate
celery -A config worker -l info

# терминал 3
source .venv/bin/activate
celery -A config beat -l info
```

Проверка задачи вручную:

```bash
celery -A config call promotions.tasks.send_weekly_discounts_task
```

Или из shell:

```python
from orders.tasks import send_delivery_reminder
send_delivery_reminder.delay(1)
```

---

## Теория: email backends

| Backend | Когда |
|---------|--------|
| `console.EmailBackend` | учёба — письма в stdout |
| `filebased.EmailBackend` + `EMAIL_FILE_PATH` | письма в файлы |
| `smtp.EmailBackend` | Gmail/Mailgun/etc. в проде |

Для сдачи курсовой достаточно console + скрин/лог, что задача вызвала `send_mail`.

---

## ✅ Ручная проверка

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `redis-cli ping` | PONG |
| ☐ | worker стартует | `ready` в логе |
| ☐ | `send_weekly_discounts_task.delay()` | письмо в консоли worker |
| ☐ | Новый заказ с `notify_before=1h` и delivery через 2 часа | в worker появится ETA-задача |
| ☐ | `send_delivery_reminder.delay(id)` | письмо + `delivery_notified=True` |

---

## 🧪 Покрытие тестами

Celery в юнит-тестах обычно гоняют в **eager**-режиме (задача выполняется синхронно, без Redis).

| Что | Файл | Проверка |
|-----|------|----------|
| weekly task | `tests/test_celery_tasks.py` | `.delay()` кладёт письмо в outbox |
| delivery reminder | там же | письмо + `delivery_notified=True` |
| schedule past eta | там же | сразу `.delay` / выполняется |
| schedule future eta | там же | `apply_async` вызван с `eta` (mock) |

```python
# tests/conftest.py — добавить
@pytest.fixture(autouse=True)
def celery_eager(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
```

```python
# tests/test_celery_tasks.py
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
import pytest
from django.core import mail
from django.utils import timezone
from orders.models import Order, NotifyBefore
from orders.tasks import send_delivery_reminder, schedule_delivery_notification
from promotions.models import NewsletterSubscription
from promotions.tasks import send_weekly_discounts_task


@pytest.mark.django_db
def test_weekly_task_sends(client_user):
    NewsletterSubscription.objects.create(user=client_user, is_active=True)
    send_weekly_discounts_task.delay()
    assert len(mail.outbox) >= 1


@pytest.mark.django_db
def test_delivery_reminder(client_user):
    order = Order.objects.create(
        user=client_user,
        total=Decimal('10.00'),
        subtotal=Decimal('10.00'),
        delivery_at=timezone.now() + timedelta(days=1),
        notify_before=NotifyBefore.DAY,
    )
    send_delivery_reminder(order.id)
    order.refresh_from_db()
    assert order.delivery_notified is True
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_schedule_future_uses_eta(client_user):
    order = Order.objects.create(
        user=client_user,
        total=Decimal('10.00'),
        subtotal=Decimal('10.00'),
        delivery_at=timezone.now() + timedelta(days=2),
        notify_before=NotifyBefore.DAY,
    )
    notify_at = timezone.now() + timedelta(days=1)
    with patch('orders.tasks.send_delivery_reminder.apply_async') as mocked:
        schedule_delivery_notification(order.id, notify_at)
        mocked.assert_called_once()
        assert mocked.call_args.kwargs['eta'] == notify_at
```

```bash
pytest tests/test_celery_tasks.py
```

**Все пункты отмечены?** → [step-17-final.md](step-17-final.md)

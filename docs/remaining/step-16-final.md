# Шаг 16 — Финальный прогон по ТЗ

**Предыдущий:** [step-15-celery-emails.md](step-15-celery-emails.md) · **Следующий:** —

## Задача

Пройти **все** пункты ТЗ сценариями через API. Если пункт не отмечен — вернуться к соответствующему шагу.

---

## 1. Карта API (итог)


| Метод | URL | Роль |
|-------|-----|------|
| GET | `/api/health/` | все |
| POST | `/api/auth/register/` | гость |
| POST/GET | `/api/auth/confirm-email/` | гость |
| POST | `/api/auth/token/` | клиент / менеджер |
| GET | `/api/products/` | все (гость — только active) |
| POST/PUT/PATCH/DELETE | `/api/products/…` | менеджер |
| CRUD | `/api/discounts/` | менеджер |
| GET/POST/PATCH/DELETE | `/api/cart/…` | клиент confirmed |
| POST | `/api/checkout/preview/` | клиент |
| GET/POST | `/api/orders/` | клиент |
| GET/POST/DELETE | `/api/newsletter/` | клиент |
| GET/PATCH | `/api/settings/` | менеджер |
| GET | `/api/wallet/` | клиент |

---

## 2. Чеклист основного ТЗ

| ☐ | Пункт ТЗ | Как проверить |
|---|----------|---------------|
| ☐ | 3 типа пользователей | гость без токена; client JWT; manager JWT |
| ☐ | Данные клиента: имя, фамилия, email, телефон | register + admin / `User` |
| ☐ | Менеджер CRUD категорий и товаров | POST/PATCH/DELETE `/api/categories/`, `/api/products/` |
| ☐ | Гость смотрит каталог | GET `/api/categories/`, `/api/products/` без Authorization |
| ☐ | Клиент смотрит и кладёт в корзину | GET products + POST `/api/cart/items/` |
| ☐ | Клиент удаляет из корзины | DELETE `/api/cart/items/{id}/` |
| ☐ | Скидки на товары менеджером | POST `/api/discounts/`, `effective_price` |
| ☐ | Подписка на рассылку раз в неделю | POST `/api/newsletter/` + Celery Beat / `send_weekly_discounts` |
| ☐ | Заказ + notify 1d / 6h / 1h | POST order с `notify_before`, задача в Celery |

---

## 3. Чеклист доп. ТЗ

| ☐ | Пункт | Как проверить |
|---|-------|---------------|
| ☐ | Регистрация с confirm email | register → письмо → confirm → `email_confirmed=True` |
| ☐ | Количество в корзине + edit | POST qty, PATCH qty |
| ☐ | Кэшбэк % от менеджера | PATCH settings, заказ → wallet↑ |
| ☐ | Списание если balance ≥ X | order с `cashback_to_use`, отказ если < X |

---

## 4. Сквозной сценарий (30 минут)

1. Поднять: Postgres, Redis, `runserver`, `celery worker`, `celery beat`.
2. Войти менеджером → создать категорию + 2 товара → скидку 20% на один → settings `percent=5`, `X=30`.
3. Зарегистрировать клиента → confirm из консоли → JWT.
4. Гостем открыть каталог (без токена).
5. Клиентом: 2 позиции в корзину, изменить qty, preview (total = сумма effective).
6. Оформить заказ с `notify_before=6h`.
7. Проверить wallet, второй заказ со списанием кэшбэка (если хватает).
8. Подписать newsletter → `python manage.py send_weekly_discounts`.
9. Убедиться, что чужой клиент не видит чужие заказы (второй пользователь).

---

## 5. Типичные ошибки


| Симптом | Причина | Что сделать |
|---------|---------|-------------|
| 401 на всё подряд | Нет `Authorization: Bearer` | получить token |
| 403 на POST products | роль CLIENT | войти менеджером |
| Гость не видит товары | забыли `get_permissions` AllowAny | шаг 6 |
| `AUTH_USER_MODEL` ошибки | User добавили после migrate | пересоздать БД (учебный проект) |
| Письма «не приходят» | смотрите не ту консоль | console backend пишет в процесс, где вызван send_mail (worker!) |
| Celery задача молчит | нет worker / неверный `-A config` | проверить лог worker |
| Неверная сумма | считают float / забыли effective_price | только Decimal + pricing service |

---

## 6. Структура файлов (ориентир)

```text
TMS_drf_online_shop/
├── manage.py
├── requirements.txt
├── .env
├── config/
│   ├── settings.py
│   ├── urls.py
│   ├── celery.py
│   └── __init__.py
├── accounts/          # User, JWT, wallet, register
├── catalog/           # Category, Product, ProductDiscount
├── cart/              # Cart, CartItem
├── orders/            # Order, tasks напоминания
├── promotions/        # Newsletter, ShopSettings, pricing
├── core/              # health, echo
└── docs/
```

---

## ✅ Готово

Если все чеклисты отмечены — приложение закрывает ТЗ «Онлайн-магазин на минималках» на Django REST Framework.

---

## 🧪 Покрытие тестами (сводка по всему проекту)

Прогоните **весь** набор перед сдачей:

```bash
pytest
# или с покрытием:
pip install pytest-cov
pytest --cov=accounts --cov=catalog --cov=cart --cov=orders --cov=promotions --cov=core
```

### Карта тестов ↔ ТЗ

| Область ТЗ | Тест-файлы (из шагов) |
|------------|------------------------|
| Окружение / smoke | `test_smoke.py` |
| Health / serializer basics | `test_core_*.py` |
| Роли, JWT | `test_auth_jwt.py`, `test_permissions.py` |
| Товары CRUD + гость | `test_products_api.py`, `test_catalog_public.py` |
| Регистрация + email | `test_registration.py` |
| Корзина qty | `test_cart_api.py` |
| Скидки на товары | `test_discounts*.py` |
| Расчёт цены | `test_pricing.py` |
| Заказ + notify | `test_orders_api.py`, `test_celery_tasks.py` |
| Рассылка | `test_newsletter.py` |
| Кэшбэк + порог X | `test_cashback*.py` |

### Минимальный «регресс» перед сдачей

| ☐ | Команда / сценарий | Ожидание |
|---|-------------------|----------|
| ☐ | `pytest -q` | все зелёные |
| ☐ | Нет тестов, помеченных `skip` без причины | — |
| ☐ | `test_pricing` — товарная скидка 100→80 | Decimal |
| ☐ | `test_catalog_public` — гость не видит скрытое | 200/404 |
| ☐ | `test_cashback` — отказ при balance < X | ValueError / 400 |

Дальше по желанию (вне ТЗ): CORS + простой фронт, платежи. Swagger уже на [шаге 7](step-07-swagger.md).
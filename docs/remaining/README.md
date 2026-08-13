# Онлайн-магазин (DRF) — пошаговая сборка

Дополнение к [guide.md](../guide.md). Каждый файл — **один этап**: теория DRF + код + **проверка API** в конце.

> **Правило:** не открывайте следующий шаг, пока не отметили все пункты «✅ Готово» в текущем.

## Порядок шагов

| # | Файл | Что делаете | Теория DRF |
|---|------|-------------|------------|
| 0 | *(этот файл)* | Обзор и команды | — |
| 1 | [step-01-env.md](step-01-env.md) | venv, requirements, PostgreSQL, Django-проект | окружение |
| 2 | [step-02-drf-basics.md](step-02-drf-basics.md) | Первый endpoint | **URL, Serializer, APIView** (читать целиком) |
| 3 | [step-03-users-roles.md](step-03-users-roles.md) | User, роли, JWT, permissions | auth vs permission в цикле view |
| 4 | [step-04-products-models.md](step-04-products-models.md) | Модели Category + Product (+ admin) | Decimal / ORM / FK |
| 5 | [step-05-products-api.md](step-05-products-api.md) | CRUD категорий и товаров (менеджер) | **ModelSerializer, ViewSet, Router** |
| 6 | [step-06-catalog-public.md](step-06-catalog-public.md) | Публичный GET для гостя | `get_permissions` / `get_queryset` / `self.action` |
| 7 | [step-07-swagger.md](step-07-swagger.md) | Swagger UI / OpenAPI | `drf-spectacular`, Authorize JWT |
| 8 | [step-08-registration-email.md](step-08-registration-email.md) | Регистрация + подтверждение email | CreateAPIView + serializer.create |
| 9 | [step-09-cart.md](step-09-cart.md) | Корзина: добавить / удалить / qty | ViewSet + `@action`, вложенные URL |
| 10 | [step-10-product-discounts.md](step-10-product-discounts.md) | Скидки на товары | вложенные serializer fields |
| 11 | [step-11-promo-codes.md](step-11-promo-codes.md) | Промокоды и флаг суммирования | lookup_field=code |
| 12 | [step-12-pricing-service.md](step-12-pricing-service.md) | Сервис расчёта итоговой суммы | service layer vs views |
| 13 | [step-13-orders.md](step-13-orders.md) | Заказ + уведомление о доставке | ReadOnlyModelViewSet + create |
| 14 | [step-14-newsletter.md](step-14-newsletter.md) | Подписка + еженедельная рассылка | APIView без модели CRUD |
| 15 | [step-15-cashback.md](step-15-cashback.md) | Кэшбэк и порог X | — |
| 16 | [step-16-celery-emails.md](step-16-celery-emails.md) | Celery Beat, консоль email | — |
| 17 | [step-17-final.md](step-17-final.md) | Чеклист ТЗ + сценарии | карта API |

> **Совет:** шаги **2, 5 и 6** — теоретический каркас. Не листайте теорию по диагонали: на них завязаны все остальные файлы.

> **Тесты:** в конце **каждого** шага — блок **🧪 Покрытие тестами** (что писать + пример кода). На шаге 1 поднимаете `pytest` + `pytest.ini`; на шаге 17 — полный прогон `pytest`.

## Что уже есть в репозитории

На старте репозиторий **пустой** — всё создаёте по шагам 1–17.

| Компонент | Статус |
|-----------|--------|
| Django + DRF + PostgreSQL | ❌ шаг 1–2 |
| User / роли / JWT | ❌ шаг 3 |
| Catalog API (категории + товары) | ❌ шаги 4–6 |
| Swagger / OpenAPI | ❌ шаг 7 |
| Регистрация + email | ❌ шаг 8 |
| Корзина | ❌ шаг 9 |
| Скидки + промокоды + pricing | ❌ шаги 10–12 |
| Заказы + рассылка + кэшбэк | ❌ шаги 13–15 |
| Celery / финальный прогон | ❌ шаги 16–17 |

## Тестовые пользователи (создадите по ходу)

| Логин / email | Роль | Когда |
|---------------|------|-------|
| `manager@shop.local` | менеджер | шаг 3–5 |
| `client@shop.local` | клиент (email confirmed) | шаг 8 |
| *(без токена)* | гость | шаг 6 |

## Быстрые команды

```bash
source .venv/bin/activate
python manage.py runserver
```

- API root / browsable: [http://127.0.0.1:8000/api/](http://127.0.0.1:8000/api/)
- Swagger UI (с шага 7): [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- Admin: [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/)

Проверка endpoint без браузера:

```bash
curl -s http://127.0.0.1:8000/api/products/ | python -m json.tool
```

## Папка `code/`

Крупные reference-файлы (по мере появления) копируйте в проект:

```bash
# примеры появятся на соответствующих шагах
cp docs/remaining/code/pricing.py promotions/services/pricing.py
```

**Старт:** [step-01-env.md](step-01-env.md)

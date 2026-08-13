# Онлайн-магазин на минималках — документация

Пошаговый гайд по разработке упрощённого **онлайн-магазина** на **Django + Django REST Framework (DRF)**.

Материал разбит на этапы в папке [`remaining/`](remaining/README.md): теория DRF → код → разбор → ручная проверка API.

## Как читать

1. Сначала [guide.md](guide.md) — что строим, роли пользователей, карта сущностей, API overview.
2. Затем строго по порядку [remaining/](remaining/README.md) — не переходите дальше, пока не отметили «✅ Готово».

Каждый технический блок устроен одинаково:

1. **Задача** — что должно получиться и зачем шаг нужен в ТЗ.
2. **Теория DRF** — концепции, без которых код «магия».
3. **Код** — что пишем в файлы.
4. **Разбор** — зачем каждая конструкция.
5. **✅ Проверка** — Swagger UI / `curl` / browsable API / shell: что должно работать **сейчас**.

## Стек

| Компонент | Зачем |
|-----------|--------|
| Django 5.x / 6.x | ORM, admin, auth, email |
| Django REST Framework | JSON API, serializers, ViewSets, permissions |
| PostgreSQL | основная БД |
| SimpleJWT (или Token) | аутентификация клиента и менеджера |
| drf-spectacular | OpenAPI-схема + Swagger UI (вместо Postman) |
| Celery + Redis | еженедельная рассылка скидок, напоминания о доставке |
| Pillow | картинки товаров (опционально) |

## Быстрый вход

```bash
cd TMS_drf_online_shop
# дальше — remaining/step-01-env.md
```

**Пошаговая сборка:** [remaining/README.md](remaining/README.md)

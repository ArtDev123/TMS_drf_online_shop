# Онлайн-магазин на минималках — обзор ТЗ и архитектуры

Пошаговая реализация — в [`remaining/`](remaining/README.md). Этот файл — **карта проекта**: роли, сущности, API, порядок сборки.

> **Правило:** не пишите код «вперёд ТЗ». Сначала поймите, *кто* что может, потом — *какая* модель и *какой* endpoint.

---

## 1. Задача из ТЗ

Создать упрощённое приложение для заказа товаров онлайн.

### 1.1. Основной функционал


| Требование ТЗ | Роль | Где в проекте |
|---------------|------|---------------|
| 3 типа пользователей: клиент, незарегистрированный, менеджер | все | `accounts` + permissions |
| Данные клиента: имя, фамилия, email, телефон | клиент | `accounts.User` / `ClientProfile` |
| CRUD товаров | менеджер | `catalog` ViewSet |
| Просмотр товаров | гость + клиент | `GET /api/products/` |
| Корзина: добавить / удалить | клиент | `cart` |
| Скидки на отдельные товары | менеджер | `catalog.ProductDiscount` |
| Подписка на рассылку скидок (1 раз/неделю) | клиент | `promotions` + Celery Beat |
| Промокод на итоговую сумму; суммирование / не суммирование со скидками товара | клиент + менеджер | `promotions.PromoCode` + pricing service |
| Форма заказа + уведомление о доставке за 1 день / 6 ч / 1 ч | клиент | `orders` + Celery |

### 1.2. Дополнительный функционал


| Требование | Где |
|------------|-----|
| Регистрация с подтверждением email | `accounts` + email backend |
| Количество товара в корзине + редактирование | `cart.CartItem.quantity` |
| Кэшбэк: % от заказа (задаёт менеджер); списание, если баланс ≥ X | `promotions.ShopSettings` + `accounts.CashbackWallet` |

---

## 2. Три типа пользователей

В REST это не три таблицы, а **уровни доступа**:


| Тип | Как представлен | Что может |
|-----|-----------------|-----------|
| **Незарегистрированный (гость)** | `request.user.is_anonymous` | Только `GET` каталога |
| **Клиент** | User с ролью `CLIENT`, email подтверждён | Каталог, корзина, заказ, подписка, кэшбэк |
| **Менеджер магазина** | User с ролью `MANAGER` (или `is_staff` + группа) | CRUD товаров, скидки, промокоды, настройки кэшбэка |

```text
Гость ──GET──► /api/products/
Клиент ──JWT──► /api/cart/, /api/orders/, /api/newsletter/
Менеджер ──JWT──► /api/products/ (POST/PUT/DELETE), /api/discounts/, /api/promo-codes/, /api/settings/
```

Один `User` в БД; роль — поле `role` или группа Django. Гость — **нет** токена.

---

## 3. Структура данных (упрощённо)

```text
User (role: CLIENT | MANAGER)
  ├── ClientProfile (first_name, last_name, phone, email_confirmed)
  ├── CashbackWallet (balance)
  ├── Cart
  │     └── CartItem → Product, quantity
  ├── Order
  │     ├── OrderItem (snapshot цены)
  │     ├── promo_code?
  │     ├── cashback_used
  │     └── notify_before (1d | 6h | 1h)
  └── NewsletterSubscription

Product
  ├── price, name, description, is_active
  └── ProductDiscount (percent | amount, active, dates)

PromoCode
  ├── code, percent/amount, is_active
  └── stackable_with_product_discount (bool)

ShopSettings (singleton)
  ├── cashback_percent
  └── cashback_min_to_spend (X)
```

**Почему snapshot в OrderItem?**  
Цена и скидка на момент заказа должны «застыть». Иначе менеджер изменит товар — и история заказов «поедет».

---

## 4. Цепочка запроса в DRF

В классическом Django:

```text
URL → View → Template → HTML
```

В DRF:

```text
URL (path / include / Router) → APIView или ViewSet → Serializer → JSON
                                        ↓
                                 Model / Service
                                        ↓
                                 PostgreSQL
```

**Где разобрано подробно в шагах:**

| Тема | Файл |
|------|------|
| `path` / `include` / `as_view`, цикл `APIView`, Serializer вход/выход | [step-02](remaining/step-02-drf-basics.md) |
| JWT встраивается в `initial()` view | [step-03](remaining/step-03-users-roles.md) |
| `ModelSerializer`, `ModelViewSet`, `DefaultRouter`, `self.action` | [step-05](remaining/step-05-products-api.md) |
| `get_permissions` / `get_queryset` по роли | [step-06](remaining/step-06-catalog-public.md) |
| `@action` для своих URL | [step-08](remaining/step-08-cart.md) |

**Пример:** клиент добавляет товар в корзину `POST /api/cart/items/`

1. Router находит action `add_item` у `CartViewSet`.
2. Permission: `IsConfirmedClient`.
3. Serializer валидирует `{ "product_id": 5, "quantity": 2 }`.
4. Service/view создаёт или обновляет `CartItem`.
5. Response: `201` + JSON корзины с пересчитанной суммой.

---

## 5. Карта API (целевая)

Базовый префикс: `/api/`.


| Метод | URL | Кто | Назначение |
|-------|-----|-----|------------|
| POST | `/auth/register/` | гость | регистрация |
| POST | `/auth/confirm-email/` | гость | подтверждение |
| POST | `/auth/token/` | клиент/менеджер | получить JWT |
| GET | `/products/` | все | список товаров |
| POST/PUT/PATCH/DELETE | `/products/`… | менеджер | CRUD |
| GET/POST/PATCH/DELETE | `/cart/`… | клиент | корзина |
| GET/POST/PUT/DELETE | `/discounts/` | менеджер | скидки на товары |
| GET/POST… | `/promo-codes/` | менеджер | промокоды |
| POST | `/orders/` | клиент | оформить заказ |
| POST | `/newsletter/subscribe/` | клиент | подписка |
| GET/PATCH | `/settings/` | менеджер | % кэшбэка и порог X |
| GET | `/wallet/` | клиент | баланс кэшбэка |

Полная таблица и сценарии — на [шаге 16](remaining/step-16-final.md).

---

## 6. Как считается итоговая цена

Это ядро бизнеса. Вынесем в **сервис** `pricing.calculate_order_total(...)` (шаг 11), а не размажем по views.

```text
1. Сумма позиций = Σ (unit_price × qty)
   unit_price = price с учётом ProductDiscount (если активна)

2. Если есть промокод:
   - если stackable_with_product_discount = True
       → скидка промокода от суммы после товарных скидок
   - если False
       → либо только товарные скидки, либо только промокод
         (в гайде: выбираем выгодный для клиента вариант
          ИЛИ жёстко «промокод отменяет суммирование» —
          зафиксируем правило на шаге 10–11)

3. Кэшбэк к списанию (если balance ≥ X и клиент запросил):
   → вычитаем min(requested, balance, total_after_discounts)

4. Итог ≥ 0
```

После успешного заказа: начисляем `total * cashback_percent / 100` на кошелёк.

---

## 7. Структура репозитория (целевая)

```text
TMS_drf_online_shop/
├── manage.py
├── .env
├── requirements.txt
├── config/                 # settings, urls, celery
├── accounts/               # User, регистрация, JWT, wallet
├── catalog/                # Product, ProductDiscount
├── cart/                   # Cart, CartItem
├── orders/                 # Order, OrderItem, уведомления
├── promotions/             # PromoCode, Newsletter, ShopSettings
├── docs/                   # этот гайд
└── scripts/init_postgres.sql
```

---

## 8. Этапы разработки


| Этап | Файл | Что реализуете |
|------|------|----------------|
| 1 | [step-01-env.md](remaining/step-01-env.md) | venv, пакеты, PostgreSQL, startproject |
| 2 | [step-02-drf-basics.md](remaining/step-02-drf-basics.md) | Теория DRF + «Hello API» |
| 3 | [step-03-users-roles.md](remaining/step-03-users-roles.md) | User, роли, JWT, permissions |
| 4 | [step-04-products-models.md](remaining/step-04-products-models.md) | Модели товаров |
| 5 | [step-05-products-api.md](remaining/step-05-products-api.md) | CRUD товаров для менеджера |
| 6 | [step-06-catalog-public.md](remaining/step-06-catalog-public.md) | Публичный каталог для гостя |
| 7 | [step-07-registration-email.md](remaining/step-07-registration-email.md) | Регистрация + confirm email |
| 8 | [step-08-cart.md](remaining/step-08-cart.md) | Корзина: add/remove/qty |
| 9 | [step-09-product-discounts.md](remaining/step-09-product-discounts.md) | Скидки на товары |
| 10 | [step-10-promo-codes.md](remaining/step-10-promo-codes.md) | Промокоды + stackable |
| 11 | [step-11-pricing-service.md](remaining/step-11-pricing-service.md) | Сервис расчёта цены |
| 12 | [step-12-orders.md](remaining/step-12-orders.md) | Заказ + remind о доставке |
| 13 | [step-13-newsletter.md](remaining/step-13-newsletter.md) | Подписка + weekly task |
| 14 | [step-14-cashback.md](remaining/step-14-cashback.md) | Кэшбэк и порог X |
| 15 | [step-15-celery-emails.md](remaining/step-15-celery-emails.md) | Сводка Celery/email |
| 16 | [step-16-final.md](remaining/step-16-final.md) | Финальный прогон по ТЗ |

**Начните здесь:** [remaining/README.md](remaining/README.md)

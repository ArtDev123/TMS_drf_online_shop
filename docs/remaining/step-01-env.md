# Шаг 1 — Окружение, PostgreSQL, Django-проект

**Предыдущий:** [README](README.md) · **Следующий:** [step-02-drf-basics.md](step-02-drf-basics.md)

## Задача

Поднять изолированное Python-окружение, БД PostgreSQL и пустой Django-проект `config`, в который на следующих шагах подключим DRF и приложения магазина.

Без этого шага остальные файлы гайда не к чему применять.

---

## Теория: зачем venv и зачем PostgreSQL

**venv** — папка с «личным» Python и пакетами проекта. Системный Django 3 и проектный Django 5 не будут конфликтовать.

**PostgreSQL** вместо SQLite:

- ближе к продакшену;
- нормальные типы (`Decimal` для денег ведёт себя предсказуемее);
- удобно смотреть данные через `psql` / DBeaver.

Для учебного API SQLite тоже «взлетит», но в гайде фиксируем PostgreSQL — как в курсовом гайде Educa.

---

## 1. Проверка инструментов

```bash
python3 --version    # желательно 3.12+
psql --version
```

Если `psql` нет — установите PostgreSQL для вашей ОС и убедитесь, что сервис запущен.

---

## 2. Создать каталог проекта и venv

```bash
cd /home/artem/Code/TMS_drf_online_shop
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

В приглашении терминала должно появиться `(.venv)`.

---

## 3. Установить зависимости

Пока ставим минимум. Celery и Redis появятся на шагах 12–15; JWT — на шаге 3.

```bash
pip install "Django>=5.1,<6.1" djangorestframework psycopg2-binary python-dotenv Pillow
```

Создайте в корне `requirements.txt`:

```text
Django>=5.1,<6.1
djangorestframework
psycopg2-binary
python-dotenv
Pillow
djangorestframework-simplejwt
celery
redis
django-celery-beat
```

Полный список можно установить сразу:

```bash
pip install -r requirements.txt
```

**Разбор пакетов:**

| Пакет | Зачем |
|-------|--------|
| `Django` | ORM, admin, auth, email, management-команды |
| `djangorestframework` | serializers, ViewSets, permissions, browsable API |
| `psycopg2-binary` | драйвер PostgreSQL для Django |
| `python-dotenv` | читать `.env` (секреты не в git) |
| `Pillow` | `ImageField` для картинок товаров |
| `djangorestframework-simplejwt` | access/refresh токены для клиента и менеджера |
| `celery` + `redis` | фоновые задачи: рассылка, напоминания о доставке |
| `django-celery-beat` | расписание «раз в неделю» из админки/кода |

---

## 4. PostgreSQL: база и пользователь

Создайте файл `scripts/init_postgres.sql`:

```sql
CREATE USER shop_user WITH PASSWORD 'shop_pass';
CREATE DATABASE shop_db OWNER shop_user;
GRANT ALL PRIVILEGES ON DATABASE shop_db TO shop_user;
ALTER USER shop_user CREATEDB;
```

Выполните (один раз):

```bash
mkdir -p scripts
sudo -u postgres psql -v ON_ERROR_STOP=1 -f scripts/init_postgres.sql
```

Проверка:

```bash
psql -h localhost -U shop_user -d shop_db -c 'SELECT 1;'
# введите пароль shop_pass → должен вернуть 1
```

> Если peer-auth мешает: используйте `-h localhost`, чтобы пошёл парольный вход через TCP.

---

## 5. Файл `.env`

В корне проекта:

```bash
cat > .env << 'EOF'
DJANGO_SECRET_KEY=dev-change-me-to-a-long-random-string
DJANGO_DEBUG=True
POSTGRES_DB=shop_db
POSTGRES_USER=shop_user
POSTGRES_PASSWORD=shop_pass
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
EOF
```

Добавьте `.env` в `.gitignore` (создайте файл, если его ещё нет):

```text
.venv/
__pycache__/
*.pyc
.env
media/
db.sqlite3
```

---

## 6. `django-admin startproject`

Проект настроек назовём `config` (не `shop` — чтобы не путать с доменным смыслом «магазин»):

```bash
django-admin startproject config .
```

Должны появиться `manage.py` и папка `config/`.

Структура сейчас:

```text
TMS_drf_online_shop/
├── manage.py
├── requirements.txt
├── .env
├── .gitignore
├── scripts/init_postgres.sql
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
└── docs/
```

---

## 7. Подключить `.env` и PostgreSQL в `settings.py`

В начале `config/settings.py` (после импортов):

```python
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'unsafe-dev-key')
DEBUG = os.getenv('DJANGO_DEBUG', 'True') == 'True'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
```

Замените блок `DATABASES` на:

```python
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB', 'shop_db'),
        'USER': os.getenv('POSTGRES_USER', 'shop_user'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'HOST': os.getenv('POSTGRES_HOST', 'localhost'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
    }
}
```

Язык и время (удобно для писем и админки):

```python
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True
```

Media (пригодится для картинок товаров):

```python
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
```

---

## 8. Первые миграции Django

```bash
python manage.py migrate
python manage.py createsuperuser
# например: admin / admin@shop.local / пароль запомните
```

---

## ✅ Ручная проверка

```bash
source .venv/bin/activate
python manage.py check
python -c "import django, rest_framework; print(django.get_version(), rest_framework.VERSION)"
python manage.py runserver
```

| ☐ | Действие | Ожидаемый результат |
|---|----------|---------------------|
| ☐ | `python manage.py check` | `System check identified no issues` |
| ☐ | Импорт Django + DRF | версии печатаются без ошибки |
| ☐ | `psql … SELECT 1` | `1` |
| ☐ | [http://127.0.0.1:8000/](http://127.0.0.1:8000/) | страница «The install worked successfully» |
| ☐ | [http://127.0.0.1:8000/admin/](http://127.0.0.1:8000/admin/) | логин суперпользователя работает |

---

## 🧪 Покрытие тестами

На этом шаге ещё нет бизнес-API — проверяем, что проект **поднимается** и настройки валидны. Дальше в каждом файле будет блок с тестами именно того функционала, который вы только что написали.

### Разовая подготовка (сделайте сейчас)

```bash
pip install pytest pytest-django
```

Добавьте в `requirements.txt`:

```text
pytest
pytest-django
```

В корне создайте `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = tests.py test_*.py *_tests.py
addopts = -q
```

Создайте пакет тестов:

```bash
mkdir -p tests
touch tests/__init__.py
```

### Что покрыть сейчас

| Что | Файл | Проверка |
|-----|------|----------|
| Django system check | `tests/test_smoke.py` | нет ошибок конфигурации |
| Подключение к БД | там же | простой `SELECT 1` через ORM/connection |

```python
# tests/test_smoke.py
import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.django_db
def test_django_check_passes():
    call_command('check')


@pytest.mark.django_db
def test_database_connection():
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1')
        assert cursor.fetchone()[0] == 1
```

```bash
pytest tests/test_smoke.py
```

**Все пункты отмечены?** → [step-02-drf-basics.md](step-02-drf-basics.md)

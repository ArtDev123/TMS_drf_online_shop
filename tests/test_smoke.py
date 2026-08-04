import pytest
from django.core.management import call_command
from django.db import connection


@pytest.mark.django_db
def test_django_check_passes():
    call_command("check")


@pytest.mark.django_db
def test_database_connection():
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1

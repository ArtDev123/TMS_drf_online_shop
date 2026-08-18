# tests/test_registration.py
import pytest
from django.core import mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from accounts.models import User, UserRole
from accounts.utils import email_token_generator


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
    token = email_token_generator.make_token(user)
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
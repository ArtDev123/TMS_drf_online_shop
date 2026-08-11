import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User, UserRole


@pytest.fixture
def manager(db):
    return User.objects.create_user(
        email='manager@test.local',
        password='pass12345',
        first_name='M',
        last_name='G',
        role=UserRole.MANAGER,
        email_confirmed=True,
    )


@pytest.fixture
def client_user(db):
    return User.objects.create_user(
        email='client@test.local',
        password='pass12345',
        first_name='C',
        last_name='L',
        role=UserRole.CLIENT,
        email_confirmed=True,
    )


@pytest.fixture
def api():
    return APIClient()


def auth_client(user):
    api = APIClient()
    token = RefreshToken.for_user(user).access_token
    api.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return api


@pytest.fixture
def manager_api(manager):
    return auth_client(manager)


@pytest.fixture
def client_api(client_user):
    return auth_client(client_user)

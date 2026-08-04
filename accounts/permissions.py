from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import UserRole, User


class IsManager(BasePermission):
    """Только менеджер магазина (или суперпользователь)."""

    def has_permission(self, request, view):
        user: User = request.user
        return bool(user and user.is_authenticated and user.is_manager)


class IsClient(BasePermission):
    """Только клиент с подтверждённым email (для заказа/корзины можно усилить)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.role == UserRole.CLIENT
        )


class IsClientOrReadOnly(BasePermission):
    """Пример комбинированного правила (пригодится позже)."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated)
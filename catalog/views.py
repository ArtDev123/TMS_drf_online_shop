from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from drf_spectacular.utils import extend_schema, extend_schema_view

from accounts.permissions import IsManager
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Category.objects.all()
        user = self.request.user
        if user.is_authenticated and getattr(user, 'is_manager', False):
            return qs
        return qs.filter(is_active=True)


@extend_schema_view(
    list=extend_schema(summary='Список товаров', tags=['catalog']),
    create=extend_schema(summary='Создать товар (менеджер)', tags=['catalog']),
    retrieve=extend_schema(summary='Карточка товара', tags=['catalog']),
)
class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related('category').all()

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Product.objects.select_related('category').all()
        user = self.request.user
        # менеджер видит всё, включая скрытые
        if not (user.is_authenticated and getattr(user, 'is_manager', False)):
            qs = qs.filter(is_active=True, category__is_active=True)

        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category_id=category)
        return qs

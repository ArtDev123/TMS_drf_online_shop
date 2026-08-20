from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from drf_spectacular.types import OpenApiTypes

from accounts.permissions import IsManager
from .models import Category, Product, ProductDiscount
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    ProductDiscountSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Category.objects.all()
        user = self.request.user
        if user.is_authenticated and getattr(user, "is_manager", False):
            return qs
        return qs.filter(is_active=True)


@extend_schema_view(
    list=extend_schema(
        summary="Список товаров",
        tags=["catalog"],
        parameters=[
            OpenApiParameter("category", OpenApiTypes.INT, OpenApiParameter.QUERY)
        ],
    ),
    retrieve=extend_schema(summary="Карточка товара", tags=["catalog"]),
)
class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related("category").prefetch_related("discounts").all()

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [AllowAny()]
        return [IsManager()]

    def get_queryset(self):
        qs = Product.objects.select_related("category").all()
        user = self.request.user
        # менеджер видит всё, включая скрытые
        if not (user.is_authenticated and getattr(user, "is_manager", False)):
            qs = qs.filter(is_active=True, category__is_active=True)

        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category_id=category)
        return qs


@extend_schema_view(
    list=extend_schema(summary='Список скидок', tags=['discounts']),
    retrieve=extend_schema(summary='Скидка', tags=['discounts']),
    create=extend_schema(summary='Создать скидку (менеджер)', tags=['discounts']),
    update=extend_schema(summary='Заменить скидку', tags=['discounts']),
    partial_update=extend_schema(summary='Изменить скидку', tags=['discounts']),
    destroy=extend_schema(summary='Удалить скидку', tags=['discounts']),
)
class ProductDiscountViewSet(viewsets.ModelViewSet):
    queryset = ProductDiscount.objects.select_related('product').all()
    serializer_class = ProductDiscountSerializer
    permission_classes = [IsManager]

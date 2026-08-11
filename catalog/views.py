from rest_framework import viewsets

from accounts.permissions import IsManager
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer


class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD категорий.
    Пока весь набор действий — только для менеджера.
    На шаге 6 откроем list/retrieve для всех.
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsManager]
    lookup_field = 'pk'


class ProductViewSet(viewsets.ModelViewSet):
    """
    CRUD товаров.
    Пока весь набор действий — только для менеджера.
    На шаге 6 откроем list/retrieve для всех.
    """

    queryset = Product.objects.select_related('category').all()
    serializer_class = ProductSerializer
    permission_classes = [IsManager]
    lookup_field = 'pk'  # можно сменить на 'slug'

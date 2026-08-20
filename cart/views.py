from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsConfirmedClient
from .models import CartItem
from .serializers import CartItemSerializer, CartSerializer
from .services import get_or_create_cart


@extend_schema_view(
    list=extend_schema(summary='Моя корзина', tags=['cart'], responses=CartSerializer),
)
class CartViewSet(viewsets.ViewSet):
    """
    GET    /api/cart/              — моя корзина
    POST   /api/cart/items/        — добавить / увеличить qty
    PATCH  /api/cart/items/{id}/   — изменить qty
    DELETE /api/cart/items/{id}/   — удалить позицию
    """

    permission_classes = [IsConfirmedClient]

    def list(self, request):
        cart = get_or_create_cart(request.user)
        return Response(CartSerializer(cart).data)

    @extend_schema(
        summary='Добавить товар в корзину',
        tags=['cart'],
        request=CartItemSerializer,
        responses={201: CartSerializer},
    )
    @action(detail=False, methods=['post'], url_path='items')
    def add_item(self, request):
        cart = get_or_create_cart(request.user)
        ser = CartItemSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        product = ser.validated_data['product']
        quantity = ser.validated_data['quantity']

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity},
        )
        if not created:
            item.quantity += quantity
            # повторная валидация склада
            if item.quantity > product.stock:
                return Response(
                    {'quantity': f'Недостаточно на складе (остаток {product.stock})'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            item.save(update_fields=['quantity'])

        return Response(CartSerializer(cart).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary='Изменить количество',
        tags=['cart'],
        methods=['PATCH'],
        parameters=[OpenApiParameter('item_id', OpenApiTypes.INT, OpenApiParameter.PATH)],
        request=CartItemSerializer,
        responses=CartSerializer,
    )
    @extend_schema(
        summary='Удалить позицию',
        tags=['cart'],
        methods=['DELETE'],
        parameters=[OpenApiParameter('item_id', OpenApiTypes.INT, OpenApiParameter.PATH)],
        request=None,
        responses=CartSerializer,
    )
    @action(
        detail=False,
        methods=['patch', 'delete'],
        url_path=r'items/(?P<item_id>[^/.]+)',
    )
    def item_detail(self, request, item_id=None):
        cart = get_or_create_cart(request.user)
        try:
            item = cart.items.select_related('product').get(pk=item_id)
        except CartItem.DoesNotExist:
            return Response({'detail': 'Нет такой позиции'}, status=status.HTTP_404_NOT_FOUND)

        if request.method == 'DELETE':
            item.delete()
            return Response(CartSerializer(cart).data)

        ser = CartItemSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        return Response(CartSerializer(cart).data)

from rest_framework import serializers

from catalog.models import Product
from catalog.services import get_effective_unit_price
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.PrimaryKeyRelatedField(
        queryset=Product.objects.filter(is_active=True),
        source='product',
        write_only=True,
    )
    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price', max_digits=10, decimal_places=2, read_only=True,
    )
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = (
            'id',
            'product_id',
            'product_name',
            'product_price',
            'quantity',
            'line_total',
        )
        read_only_fields = ('id',)

    def get_line_total(self, obj):
        return get_effective_unit_price(obj.product) * obj.quantity

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError('Количество минимум 1')
        return value

    def validate(self, attrs):
        product = attrs.get('product') or getattr(self.instance, 'product', None)
        quantity = attrs.get('quantity', getattr(self.instance, 'quantity', None))
        if product and quantity is not None and quantity > product.stock:
            raise serializers.ValidationError(
                {'quantity': f'Недостаточно на складе (остаток {product.stock})'}
            )
        return attrs


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ('id', 'items', 'total', 'updated_at')

    def get_total(self, obj):
        return sum(
            (item.product.price * item.quantity for item in obj.items.select_related('product')),
            start=0,
        )

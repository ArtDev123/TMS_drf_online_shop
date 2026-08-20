from rest_framework import serializers

from .models import Category, Product, ProductDiscount, DiscountType
from .services import get_effective_unit_price, get_active_discount


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = (
            'id',
            'name',
            'slug',
            'description',
            'is_active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')


class ProductSerializer(serializers.ModelSerializer):
    effective_price = serializers.SerializerMethodField()
    discount = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = (
            'id',
            'category',
            'name',
            'slug',
            'description',
            'price',
            'effective_price',
            'discount',
            'stock',
            'is_active',
            'image',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Цена должна быть больше 0')
        return value
    
    def get_effective_price(self, obj):
        return get_effective_unit_price(obj)
    
    def get_discount(self, obj):
        d = get_active_discount(obj)
        if not d:
            return None
        return ProductDiscountSerializer(d).data


class ProductDiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductDiscount
        fields = (
            'id', 'product', 'discount_type', 'value',
            'is_active', 'starts_at', 'ends_at', 'created_at',
        )
        read_only_fields = ('id', 'created_at')

    def validate(self, attrs):
        dtype = attrs.get('discount_type', getattr(self.instance, 'discount_type', None))
        value = attrs.get('value', getattr(self.instance, 'value', None))
        
        if dtype == DiscountType.PERCENT and value is not None and value > 100:
            raise serializers.ValidationError({'value': 'Процент ≤ 100'})
        
        product = attrs.get('product', getattr(self.instance, 'product', None))
        is_active = attrs.get('is_active', True)
        
        if product and is_active:
            qs = ProductDiscount.objects.filter(product=product, is_active=True)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    'У товара уже есть активная скидка — деактивируйте её'
                )
            
        return attrs
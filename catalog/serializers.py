from rest_framework import serializers

from .models import Category, Product


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
    class Meta:
        model = Product
        fields = (
            'id',
            'category',
            'name',
            'slug',
            'description',
            'price',
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

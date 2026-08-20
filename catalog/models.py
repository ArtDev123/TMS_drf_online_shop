from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to='products/%Y/%m/%d')

    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name='products')

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']


class DiscountType(models.TextChoices):
    PERCENT = 'PERCENT', 'Процент'
    FIXED = 'FIXED', 'Фиксированная сумма'


class ProductDiscount(models.Model):
    product = models.ForeignKey(
        Product,
        related_name='discounts',
        on_delete=models.CASCADE,
    )
    discount_type = models.CharField(
        max_length=16,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text='Процент (0–100) или сумма в валюте магазина',
    )
    is_active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.product}: {self.value} ({self.discount_type})'

    def is_currently_active(self):
        if not self.is_active:
            return False
        now = timezone.now()
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    def apply_to_price(self, price):
        """Вернуть цену после скидки (Decimal)."""
        from decimal import Decimal, ROUND_HALF_UP
        price = Decimal(price)
        if self.discount_type == DiscountType.PERCENT:
            # value=10 → минус 10%
            if self.value > 100:
                raise ValueError('Процент не может быть > 100')
            factor = (Decimal('100') - self.value) / Decimal('100')
            result = price * factor
        else:
            result = price - self.value
        if result < 0:
            result = Decimal('0')
        return result.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

from django.conf import settings
from django.db import models


class Cart(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='cart',
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Cart<{self.user}>'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey('catalog.Product', on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'product'],
                name='unique_cart_product',
            ),
        ]

    def __str__(self):
        return f'{self.product} × {self.quantity}'
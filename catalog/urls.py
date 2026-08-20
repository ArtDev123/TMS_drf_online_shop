from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, ProductDiscountViewSet

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('products', ProductViewSet, basename='product')
router.register('discounts', ProductDiscountViewSet, basename='discount')

urlpatterns = router.urls

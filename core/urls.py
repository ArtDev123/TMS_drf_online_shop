from django.urls import path, include

from rest_framework.routers import DefaultRouter

from .views import EchoView, HealthView, TestModelViewSet

router = DefaultRouter()
router.register(r"test", TestModelViewSet, basename="test")

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("echo/", EchoView.as_view(), name="echo"),
    # path("test/", TestView.as_view(), name="test"),
    # path("test/<int:pk>/", TestDetailView.as_view(), name="test_detail"),
    path("", include(router.urls)),
]

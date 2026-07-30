from django.urls import path

from .views import EchoView, HealthView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("echo/", EchoView.as_view(), name="echo"),
]

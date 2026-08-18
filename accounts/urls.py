from django.urls import path

from .views import ConfirmEmailView, EmailTokenObtainPairView, RegisterView
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('auth/register/', RegisterView.as_view()),
    path('auth/confirm-email/', ConfirmEmailView.as_view()),
    path('auth/token/', EmailTokenObtainPairView.as_view()),
    path('auth/token/refresh/', TokenRefreshView.as_view()),
]

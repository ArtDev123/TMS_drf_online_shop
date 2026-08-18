from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import (
    ConfirmEmailSerializer,
    EmailTokenObtainPairSerializer,
    RegisterSerializer,
)
from .services import send_confirmation_email
from .utils import confirm_user_email


class EmailTokenObtainPairView(TokenObtainPairView):
    serializer_class = EmailTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        send_confirmation_email(user)


class ConfirmEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        ser = ConfirmEmailSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ok, msg = confirm_user_email(ser.validated_data['uid'], ser.validated_data['token'])
        return Response({'detail': msg}, status=200 if ok else 400)

    def get(self, request):
        ok, msg = confirm_user_email(
            request.query_params.get('uid', ''),
            request.query_params.get('token', ''),
        )
        return Response({'detail': msg}, status=200 if ok else 400)
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import EchoSerializer


class HealthView(APIView):
    def get(self, request):
        return Response(
            {
                "status": "ok",
                "service": "online-shop",
                "user": str(request.user),
            }
        )


class EchoView(APIView):
    """Демонстрация валидации входа через Serializer."""

    def post(self, request):
        serializer = EchoSerializer(data=request.data)
        print(f"{request.data=}")
        serializer.is_valid(raise_exception=True)
        print(serializer.validated_data)
        return Response(
            {"echo": serializer.validated_data.get("message")},
            status=status.HTTP_200_OK,
        )

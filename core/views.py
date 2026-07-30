from django.shortcuts import get_object_or_404

from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import TestModel
from .serializers import EchoSerializer, TestSerializer



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


# class TestView(APIView):
#
#     def get(self, request):
#         tests = TestModel.objects.all()
#         serializer = TestSerializer(tests, many=True)
#
#         return Response(serializer.data)
#
#     def post(self, request):
#         serializer = TestSerializer(data=request.data)
#         serializer.is_valid(raise_exception=True)
#         serializer.save()
#
#         return Response(serializer.data)
#
#
# class TestDetailView(APIView):
#
#     def get(self, request, pk):
#         test = get_object_or_404(TestModel, pk=pk)
#         serializer = TestSerializer(test, many=False)
#         return Response(serializer.data)


class TestModelViewSet(viewsets.ModelViewSet):
    queryset = TestModel.objects.all()
    serializer_class = TestSerializer

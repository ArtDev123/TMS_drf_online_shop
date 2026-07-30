from rest_framework import serializers

from core.models import TestModel


class EchoSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)


class TestSerializer(serializers.ModelSerializer):

    class Meta:
        model = TestModel
        fields = "__all__"

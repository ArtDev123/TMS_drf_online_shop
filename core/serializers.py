from rest_framework import serializers


class EchoSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=200)

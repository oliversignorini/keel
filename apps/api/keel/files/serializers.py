from rest_framework import serializers

from keel.files.models import FileUpload


class PresignedUploadRequestSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=255)
    content_type = serializers.CharField(max_length=255)
    size = serializers.IntegerField(min_value=1)


class FileUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileUpload
        fields = ("id", "key", "content_type", "size", "status", "created_at")
        read_only_fields = fields

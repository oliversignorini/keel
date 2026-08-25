"""Shape validation at the edge (PRD §4, "What is the validation
boundary?"; docs/plans/phase-6.md 6.D)."""

from rest_framework import serializers

from keel.widgets.models import Widget


class WidgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Widget
        fields = ("id", "name", "description", "status", "created_by", "created_at", "updated_at")
        read_only_fields = ("id", "created_by", "created_at", "updated_at")


class WidgetWriteSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    status = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")


class WidgetUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)

"""Serializer for the audit read surface (PRD §7; docs/plans/phase-8.md
8.2)."""

from rest_framework import serializers

from keel.audit.models import AuditLog


class _AuditActorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField()


class AuditLogSerializer(serializers.ModelSerializer):
    actor = _AuditActorSerializer(read_only=True, allow_null=True)
    impersonator = _AuditActorSerializer(read_only=True, allow_null=True)

    class Meta:
        model = AuditLog
        fields = (
            "id",
            "action",
            "actor",
            "impersonator",
            "target_type",
            "target_id",
            "metadata",
            "ip",
            "created_at",
        )
        read_only_fields = fields

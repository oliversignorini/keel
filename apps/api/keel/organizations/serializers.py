"""Serializers for the organisations/members/roles/invitations API
(PRD §7)."""

from typing import Any

from django.utils.text import slugify
from rest_framework import serializers

from keel.organizations.models import Invitation, Membership, Organization, Role


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "created_at", "updated_at")
        read_only_fields = ("id", "slug", "created_at", "updated_at")


class OrganizationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    slug = serializers.SlugField(max_length=255, required=False)

    def validate_slug(self, value: str) -> str:
        if Organization.objects.filter(slug=value).exists():
            raise serializers.ValidationError("An organisation with this slug already exists.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not attrs.get("slug"):
            attrs["slug"] = self._unique_slug(slugify(attrs["name"]))
        return attrs

    @staticmethod
    def _unique_slug(base: str) -> str:
        base = base or "organisation"
        candidate = base
        suffix = 1
        while Organization.objects.filter(slug=candidate).exists():
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate


class OrganizationUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255, required=False)


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ("id", "name", "permissions", "is_preset")
        read_only_fields = fields


class _UserSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    name = serializers.CharField()


class MembershipSerializer(serializers.ModelSerializer):
    user = _UserSummarySerializer(read_only=True)
    role = RoleSerializer(read_only=True)

    class Meta:
        model = Membership
        fields = ("id", "user", "role", "status", "joined_at")
        read_only_fields = ("id", "user", "status", "joined_at")


class MembershipRoleUpdateSerializer(serializers.Serializer):
    role_id = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())


class InvitationSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    invited_by = _UserSummarySerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = (
            "id",
            "email",
            "role",
            "invited_by",
            "expires_at",
            "accepted_at",
            "revoked_at",
            "status",
            "created_at",
        )
        read_only_fields = fields

    def get_status(self, invitation: Invitation) -> str:
        from django.utils import timezone

        if invitation.accepted_at is not None:
            return "accepted"
        if invitation.revoked_at is not None:
            return "revoked"
        if invitation.expires_at <= timezone.now():
            return "expired"
        return "pending"


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role_id = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())

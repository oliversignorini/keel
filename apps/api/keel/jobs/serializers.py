"""Shape validation at the edge (PRD §4 invariant 6)."""

from rest_framework import serializers

from keel.jobs.models import Job, JobStep


class JobStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobStep
        fields = (
            "id",
            "name",
            "ordinal",
            "status",
            "output_ref",
            "started_at",
            "finished_at",
            "error",
        )


class JobSerializer(serializers.ModelSerializer):
    steps = JobStepSerializer(many=True, read_only=True)

    class Meta:
        model = Job
        fields = (
            "id",
            "type",
            "status",
            "params",
            "result_ref",
            "error",
            "created_at",
            "started_at",
            "finished_at",
            "steps",
        )


class JobCreateSerializer(serializers.Serializer):
    type = serializers.CharField()
    params = serializers.JSONField(required=False, default=dict)

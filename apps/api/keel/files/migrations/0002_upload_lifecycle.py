# Phase 13 (docs/plans/phase-13.md): the one migration this phase is
# allowed to declare, covering every field it adds. See keel/files/models.py
# for the state machine this backs and the reasoning behind each
# constraint below (ddia#21, ddia review "Schema evolution" §23).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("files", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fileupload",
            name="filename",
            field=models.CharField(default="", max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="fileupload",
            name="checksum_sha256",
            field=models.CharField(default="0" * 64, max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="fileupload",
            name="etag",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="fileupload",
            name="failure_reason",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="fileupload",
            name="completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fileupload",
            name="deleted_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fileupload",
            name="object_purged",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="fileupload",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("available", "Available"),
                    ("failed", "Failed"),
                    ("expired", "Expired"),
                    ("deleted", "Deleted"),
                ],
                default="pending",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="fileupload",
            name="organization",
            # ddia#21 "reconsider organization CASCADE on FileUpload":
            # PROTECT instead of the OrgScopedModel-inherited CASCADE, so
            # a hard-deleted Organization can never silently orphan a
            # storage object with no tombstone left to clean it up.
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                to="organizations.organization",
            ),
        ),
        migrations.AddIndex(
            model_name="fileupload",
            index=models.Index(fields=["status", "created_at"], name="files_fileu_status_bdbf4f_idx"),
        ),
        migrations.AddConstraint(
            model_name="fileupload",
            constraint=models.CheckConstraint(
                condition=models.Q(size__gte=0), name="file_upload_size_non_negative"
            ),
        ),
        migrations.AddConstraint(
            model_name="fileupload",
            constraint=models.CheckConstraint(
                condition=models.Q(checksum_sha256__regex="^[0-9a-f]{64}$"),
                name="file_upload_checksum_sha256_is_hex64",
            ),
        ),
        migrations.AddConstraint(
            model_name="fileupload",
            constraint=models.CheckConstraint(
                condition=models.Q(("deleted_at__isnull", True)) | models.Q(status="deleted"),
                name="file_upload_deleted_at_requires_deleted_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="fileupload",
            constraint=models.CheckConstraint(
                condition=models.Q(("completed_at__isnull", True))
                | models.Q(status__in=("available", "deleted")),
                name="file_upload_completed_at_requires_reached_available",
            ),
        ),
    ]

from django.db import migrations, models


def backfill_started_at(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")
    TaskHistory = apps.get_model("tasks", "TaskHistory")

    for task in (
        Task.objects
        .filter(started_at__isnull=True)
        .only("id")
        .iterator()
    ):
        first_start = (
            TaskHistory.objects
            .filter(
                task_id=task.pk,
                field_name="status",
                new_value="in_progress",
            )
            .order_by("created_at", "pk")
            .first()
        )

        if first_start:
            Task.objects.filter(
                pk=task.pk,
                started_at__isnull=True,
            ).update(
                started_at=first_start.created_at,
            )


def reverse_backfill(apps, schema_editor):
    # No destructive reverse data operation is needed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0005_telegram_notifications"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="started_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.RunPython(
            backfill_started_at,
            reverse_backfill,
        ),
    ]

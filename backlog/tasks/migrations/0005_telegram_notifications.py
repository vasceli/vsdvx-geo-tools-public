import django.db.models.deletion
import django.utils.timezone

from django.db import migrations, models
from django.utils import timezone


def backfill_notification_state(apps, schema_editor):
    Employee = apps.get_model("tasks", "Employee")
    Task = apps.get_model("tasks", "Task")

    employees = {
        employee.username: employee.pk
        for employee in Employee.objects.all()
    }

    technical_ids = {
        employee_id
        for username, employee_id in employees.items()
        if username in {"backlog_import", "admin"}
    }

    reporter_map = {
        "Василий": "vasiliy",
        "Вася": "vasiliy",
        "Дима": "dmitry",
        "Дмитрий": "dmitry",
        "Лера": "lera",
        "Оля": "olga",
        "Ольга": "olga",
    }

    now = timezone.now()

    for task in Task.objects.all().iterator():
        updates = {}

        reporter_employee_id = None

        if (
            task.created_by_id
            and task.created_by_id not in technical_ids
        ):
            reporter_employee_id = task.created_by_id
        else:
            username = reporter_map.get(
                (task.reporter or "").strip()
            )

            if username:
                reporter_employee_id = employees.get(
                    username
                )

        if reporter_employee_id:
            updates["reporter_employee_id"] = (
                reporter_employee_id
            )

        if (
            task.due_at
            and task.due_at < now
            and task.status not in {
                "done",
                "cancelled",
            }
        ):
            updates[
                "telegram_overdue_notified_for"
            ] = task.due_at

        if updates:
            Task.objects.filter(
                pk=task.pk
            ).update(**updates)


class Migration(migrations.Migration):
    dependencies = [
        (
            "tasks",
            "0004_employee_telegram_linked_at_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="reporter_employee",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="reported_tasks",
                to="tasks.employee",
            ),
        ),
        migrations.AddField(
            model_name="task",
            name="telegram_overdue_notified_for",
            field=models.DateTimeField(
                blank=True,
                null=True,
            ),
        ),
        migrations.CreateModel(
            name="TelegramOutbox",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            (
                                "assigned",
                                "Назначена",
                            ),
                            (
                                "status_changed",
                                "Изменён статус",
                            ),
                            (
                                "completed",
                                "Завершена",
                            ),
                            (
                                "overdue",
                                "Просрочена",
                            ),
                        ],
                        max_length=30,
                    ),
                ),
                (
                    "dedupe_key",
                    models.CharField(
                        max_length=255,
                        unique=True,
                    ),
                ),
                (
                    "payload",
                    models.JSONField(
                        blank=True,
                        default=dict,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "available_at",
                    models.DateTimeField(
                        default=django.utils.timezone.now,
                    ),
                ),
                (
                    "sent_at",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                    ),
                ),
                (
                    "attempts",
                    models.PositiveIntegerField(
                        default=0,
                    ),
                ),
                (
                    "last_error",
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    "recipient",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models.deletion.PROTECT
                        ),
                        related_name="telegram_outbox",
                        to="tasks.employee",
                    ),
                ),
                (
                    "task",
                    models.ForeignKey(
                        on_delete=(
                            django.db.models.deletion.CASCADE
                        ),
                        related_name="telegram_outbox",
                        to="tasks.task",
                    ),
                ),
            ],
            options={
                "ordering": ["created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="telegramoutbox",
            index=models.Index(
                fields=[
                    "sent_at",
                    "available_at",
                ],
                name="tg_outbox_pending_idx",
            ),
        ),
        migrations.RunPython(
            backfill_notification_state,
            migrations.RunPython.noop,
        ),
    ]

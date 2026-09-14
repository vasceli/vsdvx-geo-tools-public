import re

from django.db import transaction

from .models import Task, TaskHistory


TASK_CODE_RE = re.compile(r"^TASK-(\d+)$")


def next_task_code():
    max_number = 0

    for code in Task.objects.values_list("code", flat=True):
        match = TASK_CODE_RE.match(code or "")
        if match:
            max_number = max(max_number, int(match.group(1)))

    return f"TASK-{max_number + 1:03d}"


def record_changes(*, task, actor, before, fields):
    history = []

    for field in fields:
        old_value = before.get(field)
        new_value = getattr(task, field)

        if field == "assignee_id":
            new_value = task.assignee_id

        if old_value == new_value:
            continue

        history.append(
            TaskHistory(
                task=task,
                actor=actor,
                field_name=field,
                old_value="" if old_value is None else str(old_value),
                new_value="" if new_value is None else str(new_value),
            )
        )

    if history:
        TaskHistory.objects.bulk_create(history)


@transaction.atomic
def create_task(*, employee, cleaned_data):
    task = Task.objects.create(
        code=next_task_code(),
        created_by=employee,
        reporter_employee=employee,
        priority=Task.Priority.WAITING,
        status=Task.Status.NEW,
        **cleaned_data,
    )

    TaskHistory.objects.create(
        task=task,
        actor=employee,
        field_name="created",
        old_value="",
        new_value=task.code,
    )

    return task

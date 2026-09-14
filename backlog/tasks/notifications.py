import os

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import Task, TelegramOutbox
from .telegram import send_message


TERMINAL_STATUSES = {
    Task.Status.DONE,
    Task.Status.CANCELLED,
}


def employee_name(employee):
    if not employee:
        return "—"

    return employee.display_name or employee.username


def linked(employee):
    return bool(
        employee
        and employee.is_active
        and employee.telegram_chat_id
    )


def status_label(value):
    try:
        return Task.Status(value).label
    except ValueError:
        return value or "—"


def priority_label(value):
    try:
        return Task.Priority(value).label
    except ValueError:
        return value or "—"


def deadline_label(task):
    if not task.due_at:
        return "не указан"

    return timezone.localtime(
        task.due_at
    ).strftime("%d.%m.%Y %H:%M")


def task_snapshot(task):
    return {
        "task_id": task.pk,
        "code": task.code,
        "title": task.title,
        "status": task.status,
        "status_label": status_label(task.status),
        "priority_label": priority_label(task.priority),
        "due_at": (
            task.due_at.isoformat()
            if task.due_at
            else ""
        ),
        "due_label": deadline_label(task),
        "assignee": employee_name(task.assignee),
        "reporter": employee_name(
            task.reporter_employee
        ),
    }


def event_revision(task):
    return task.updated_at.isoformat()


def enqueue_event(
    *,
    task,
    recipient,
    event_type,
    revision,
    payload,
):
    if not linked(recipient):
        return False

    dedupe_key = (
        f"{event_type}:"
        f"{task.pk}:"
        f"{recipient.pk}:"
        f"{revision}"
    )

    _, created = TelegramOutbox.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={
            "recipient": recipient,
            "task": task,
            "event_type": event_type,
            "payload": payload,
        },
    )

    return created


def enqueue_assignment(
    *,
    task,
    actor,
    previous_assignee_id,
):
    if (
        not task.assignee_id
        or task.assignee_id == previous_assignee_id
    ):
        return 0

    base_payload = task_snapshot(task)
    base_payload.update({
        "actor": employee_name(actor),
        "assigned_to": employee_name(task.assignee),
    })

    revision = event_revision(task)
    count = 0

    assignee_payload = {
        **base_payload,
        "recipient_kind": "assignee",
    }

    if enqueue_event(
        task=task,
        recipient=task.assignee,
        event_type=TelegramOutbox.EventType.ASSIGNED,
        revision=revision,
        payload=assignee_payload,
    ):
        count += 1

    for recipient in watcher_recipients(
        task,
        actor=actor,
    ):
        if recipient.pk == task.assignee_id:
            continue

        watcher_payload = {
            **base_payload,
            "recipient_kind": "watcher",
        }

        if enqueue_event(
            task=task,
            recipient=recipient,
            event_type=TelegramOutbox.EventType.ASSIGNED,
            revision=revision,
            payload=watcher_payload,
        ):
            count += 1

    return count



def watcher_recipients(
    task,
    *,
    actor=None,
):
    recipients = {}

    watcher_links = (
        task.watcher_links
        .select_related("employee")
        .all()
    )

    for watcher_link in watcher_links:
        employee = watcher_link.employee

        if not linked(employee):
            continue

        if (
            actor
            and employee.pk == actor.pk
        ):
            continue

        recipients[employee.pk] = employee

    return list(recipients.values())


def participant_recipients(
    task,
    *,
    actor=None,
):
    recipients = {}

    for employee in [
        task.assignee,
        task.reporter_employee,
    ]:
        if not linked(employee):
            continue

        if (
            actor
            and employee.pk == actor.pk
        ):
            continue

        recipients[employee.pk] = employee

    for employee in watcher_recipients(
        task,
        actor=actor,
    ):
        recipients[employee.pk] = employee

    return list(recipients.values())


def enqueue_status_change(
    *,
    task,
    actor,
    old_status,
):
    if old_status == task.status:
        return 0

    if task.status in TERMINAL_STATUSES:
        return 0

    payload = task_snapshot(task)
    payload.update({
        "actor": employee_name(actor),
        "old_status": old_status,
        "old_status_label": status_label(old_status),
        "new_status": task.status,
        "new_status_label": status_label(task.status),
    })

    count = 0
    revision = event_revision(task)

    for recipient in participant_recipients(
        task,
        actor=actor,
    ):
        if enqueue_event(
            task=task,
            recipient=recipient,
            event_type=(
                TelegramOutbox.EventType.STATUS_CHANGED
            ),
            revision=revision,
            payload=payload,
        ):
            count += 1

    return count


def enqueue_completion(
    *,
    task,
    actor,
    old_status,
):
    if task.status not in TERMINAL_STATUSES:
        return 0

    if old_status == task.status:
        return 0

    payload = task_snapshot(task)
    payload.update({
        "actor": employee_name(actor),
        "old_status_label": status_label(old_status),
        "completion_status_label": status_label(
            task.status
        ),
        "result": task.completion_comment or "",
        "result_url": task.completion_url or "",
    })

    count = 0
    revision = event_revision(task)

    for recipient in participant_recipients(
        task,
        actor=actor,
    ):
        if enqueue_event(
            task=task,
            recipient=recipient,
            event_type=TelegramOutbox.EventType.COMPLETED,
            revision=revision,
            payload=payload,
        ):
            count += 1

    return count



def enqueue_comment(
    *,
    task,
    actor,
    comment,
):
    payload = task_snapshot(task)
    payload.update({
        "actor": employee_name(actor),
        "comment": comment.body,
    })

    revision = (
        f"{comment.pk}:"
        f"{comment.created_at.isoformat()}"
    )

    count = 0

    for recipient in participant_recipients(
        task,
        actor=actor,
    ):
        if enqueue_event(
            task=task,
            recipient=recipient,
            event_type=TelegramOutbox.EventType.COMMENTED,
            revision=revision,
            payload=payload,
        ):
            count += 1

    return count


@transaction.atomic
def enqueue_overdue_tasks():
    now = timezone.now()
    count = 0

    tasks = (
        Task.objects
        .filter(
            due_at__lt=now,
        )
        .exclude(
            status__in=TERMINAL_STATUSES,
        )
        .select_related(
            "assignee",
            "reporter_employee",
        )
        .order_by("due_at")
    )

    for task in tasks:
        if (
            task.telegram_overdue_notified_for
            == task.due_at
        ):
            continue

        payload = task_snapshot(task)

        revision = (
            task.due_at.isoformat()
            if task.due_at
            else "no-deadline"
        )

        for recipient in participant_recipients(
            task
        ):
            if enqueue_event(
                task=task,
                recipient=recipient,
                event_type=(
                    TelegramOutbox.EventType.OVERDUE
                ),
                revision=revision,
                payload=payload,
            ):
                count += 1

        Task.objects.filter(
            pk=task.pk,
            due_at=task.due_at,
        ).update(
            telegram_overdue_notified_for=(
                task.due_at
            )
        )

    return count


def clipped(value, limit=1200):
    value = (value or "").strip()

    if len(value) <= limit:
        return value

    return value[:limit] + "…"


def render_message(item):
    payload = item.payload
    code = payload.get("code", "")
    title = payload.get("title", "")
    due = payload.get("due_label", "не указан")

    if (
        item.event_type
        == TelegramOutbox.EventType.ASSIGNED
    ):
        if (
            payload.get("recipient_kind")
            in {"reporter", "watcher"}
        ):
            return (
                f"👤 {code} · Назначен исполнитель\n\n"
                f"{title}\n\n"
                f"Исполнитель: "
                f"{payload.get('assigned_to', '—')}\n"
                f"Статус: "
                f"{payload.get('status_label', '—')}\n"
                f"Срок: {due}"
            )

        return (
            f"📌 Вам назначена задача {code}\n\n"
            f"{title}\n\n"
            f"Статус: "
            f"{payload.get('status_label', '—')}\n"
            f"Приоритет: "
            f"{payload.get('priority_label', '—')}\n"
            f"Срок: {due}"
        )

    if (
        item.event_type
        == TelegramOutbox.EventType.STATUS_CHANGED
    ):
        return (
            f"🔄 {code} · Изменён статус\n\n"
            f"{title}\n\n"
            f"{payload.get('old_status_label', '—')}"
            f" → "
            f"{payload.get('new_status_label', '—')}\n"
            f"Изменил: "
            f"{payload.get('actor', '—')}"
        )

    if (
        item.event_type
        == TelegramOutbox.EventType.COMPLETED
    ):
        result = clipped(
            payload.get("result", "")
        )

        text = (
            f"✅ {code} · "
            f"{payload.get('completion_status_label', 'Завершена')}"
            f"\n\n{title}"
        )

        if result:
            text += f"\n\nРезультат:\n{result}"

        text += (
            f"\n\nИзменил: "
            f"{payload.get('actor', '—')}"
        )

        return text

    if (
        item.event_type
        == TelegramOutbox.EventType.COMMENTED
    ):
        comment = clipped(
            payload.get("comment", "")
        )

        return (
            f"💬 {code} · Новый комментарий\n\n"
            f"{title}\n\n"
            f"{comment}\n\n"
            f"Автор: "
            f"{payload.get('actor', '—')}"
        )

    if (
        item.event_type
        == TelegramOutbox.EventType.OVERDUE
    ):
        return (
            f"⏰ Просрочена задача {code}\n\n"
            f"{title}\n\n"
            f"Исполнитель: "
            f"{payload.get('assignee', '—')}\n"
            f"Срок: {due}\n"
            f"Статус: "
            f"{payload.get('status_label', '—')}"
        )

    return (
        f"{code}\n\n"
        f"{title}"
    )


def task_keyboard(task_id):
    base_url = os.environ[
        "BACKLOG_BASE_URL"
    ].rstrip("/")

    return {
        "inline_keyboard": [
            [
                {
                    "text": "Открыть задачу",
                    "url": (
                        f"{base_url}/tasks/"
                        f"{task_id}/"
                    ),
                }
            ]
        ]
    }


def deliver_pending_outbox(limit=50):
    now = timezone.now()

    items = list(
        TelegramOutbox.objects
        .filter(
            sent_at__isnull=True,
            available_at__lte=now,
        )
        .select_related(
            "recipient",
            "task",
        )
        .order_by("created_at")[:limit]
    )

    sent = 0
    failed = 0

    for item in items:
        chat_id = item.recipient.telegram_chat_id

        if not chat_id:
            item.sent_at = timezone.now()
            item.last_error = (
                "Skipped: recipient Telegram is not linked."
            )
            item.attempts += 1

            item.save(
                update_fields=[
                    "sent_at",
                    "last_error",
                    "attempts",
                ]
            )
            continue

        try:
            send_message(
                chat_id,
                render_message(item),
                reply_markup=task_keyboard(
                    item.task_id
                ),
            )

        except Exception as exc:
            item.attempts += 1

            delay = min(
                300,
                2 ** min(item.attempts, 8),
            )

            item.available_at = (
                timezone.now()
                + timedelta(seconds=delay)
            )

            item.last_error = clipped(
                str(exc),
                2000,
            )

            item.save(
                update_fields=[
                    "attempts",
                    "available_at",
                    "last_error",
                ]
            )

            failed += 1
            continue

        item.sent_at = timezone.now()
        item.attempts += 1
        item.last_error = ""

        item.save(
            update_fields=[
                "sent_at",
                "attempts",
                "last_error",
            ]
        )

        sent += 1

    return sent, failed

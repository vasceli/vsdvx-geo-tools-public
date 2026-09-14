from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def format_duration(value):
    """Human-readable duration for Backlog UI."""
    if value is None:
        return ""

    total_minutes = max(
        0,
        int(value.total_seconds() // 60),
    )

    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)

    parts = []

    if days:
        parts.append(f"{days} дн.")

    if hours:
        parts.append(f"{hours} ч.")

    if minutes or not parts:
        parts.append(f"{minutes} мин.")

    return " ".join(parts)



def russian_plural(value, one, few, many):
    value = abs(value) % 100

    if 11 <= value <= 14:
        return many

    last = value % 10

    if last == 1:
        return one

    if 2 <= last <= 4:
        return few

    return many


def format_overdue_duration(value):
    if value is None:
        return ""

    total_minutes = max(
        1,
        int(value.total_seconds() // 60),
    )

    days, remainder = divmod(
        total_minutes,
        24 * 60,
    )
    hours, minutes = divmod(
        remainder,
        60,
    )

    parts = []

    if days:
        parts.append(
            f"{days} "
            f"{russian_plural(days, 'день', 'дня', 'дней')}"
        )

        if hours:
            parts.append(f"{hours} ч.")

    elif hours:
        parts.append(f"{hours} ч.")

        if minutes:
            parts.append(f"{minutes} мин.")

    else:
        parts.append(f"{minutes} мин.")

    return "Просрочено " + " ".join(parts)


class Employee(models.Model):
    class Role(models.TextChoices):
        MEMBER = "member", "Сотрудник"
        MANAGER = "manager", "Руководитель"

    username = models.CharField(max_length=150, unique=True)
    display_name = models.CharField(max_length=200, blank=True)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.MEMBER,
    )
    is_active = models.BooleanField(default=True)

    telegram_user_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
    )

    telegram_chat_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
    )

    telegram_username = models.CharField(
        max_length=100,
        blank=True,
    )

    telegram_linked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["display_name", "username"]

    def __str__(self):
        return self.display_name or self.username

    @property
    def is_manager(self):
        return self.role == self.Role.MANAGER

    @property
    def is_system_admin(self):
        return self.username == "admin"

    @property
    def can_manage_tasks(self):
        return self.is_manager or self.is_system_admin


class Task(models.Model):
    class Priority(models.TextChoices):
        WAITING = "waiting", "Ожидает оценки"
        P0 = "p0", "P0 — критично"
        P1 = "p1", "P1 — высокий"
        P2 = "p2", "P2 — средний"
        P3 = "p3", "P3 — низкий"
        STOP = "stop", "Стоп"

    class Status(models.TextChoices):
        IDEA = "idea", "Идея"
        NEW = "new", "Новая"
        PLANNED = "planned", "Запланирована"
        IN_PROGRESS = "in_progress", "В работе"
        BLOCKED = "blocked", "Заблокирована"
        REVIEW = "review", "На проверке"
        DONE = "done", "Готово"
        CANCELLED = "cancelled", "Отменена"

    code = models.CharField(
        max_length=20,
        unique=True,
    )

    title = models.CharField(max_length=500)

    acceptance_criteria = models.TextField(blank=True)

    reporter = models.CharField(
        max_length=200,
        blank=True,
    )

    reporter_employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="reported_tasks",
        null=True,
        blank=True,
    )

    direction = models.CharField(
        max_length=100,
        blank=True,
    )

    created_by = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="created_tasks",
    )

    assignee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
        null=True,
        blank=True,
    )

    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.WAITING,
    )

    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.NEW,
    )

    due_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    estimate_hours = models.DecimalField(
        max_digits=7,
        decimal_places=2,
        null=True,
        blank=True,
    )

    blockers = models.TextField(blank=True)
    next_step = models.TextField(blank=True)
    materials_url = models.TextField(blank=True)
    comment = models.TextField(blank=True)

    completion_comment = models.TextField(
        blank=True,
    )

    completion_url = models.URLField(
        max_length=1000,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    started_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    updated_at = models.DateTimeField(auto_now=True)

    completed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    telegram_overdue_notified_for = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Exact source row preserved during one-time migration from Google Sheets.
    source_data = models.JSONField(
        default=dict,
        blank=True,
    )

    @property
    def is_overdue(self):
        return bool(
            self.due_at
            and self.status not in [
                self.Status.DONE,
                self.Status.CANCELLED,
            ]
            and self.due_at < timezone.now()
        )

    @property
    def overdue_duration(self):
        if not self.is_overdue:
            return None

        return timezone.now() - self.due_at

    @property
    def overdue_display(self):
        return format_overdue_duration(
            self.overdue_duration
        )

    @property
    def total_duration(self):
        if not self.completed_at:
            return None

        return self.completed_at - self.created_at

    @property
    def work_duration(self):
        if not self.completed_at or not self.started_at:
            return None

        return self.completed_at - self.started_at

    @property
    def total_duration_display(self):
        return format_duration(self.total_duration)

    @property
    def work_duration_display(self):
        return format_duration(self.work_duration)

    class Meta:
        ordering = [
            "priority",
            "due_at",
            "-created_at",
        ]

    def __str__(self):
        return f"{self.code}: {self.title}"


class TaskHistory(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="history",
    )

    actor = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="task_changes",
    )

    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]




class SavedTaskFilter(models.Model):
    class Scope(models.TextChoices):
        MY = "my", "Мои задачи"
        ALL = "all", "Все задачи"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="saved_task_filters",
    )

    name = models.CharField(max_length=100)

    scope = models.CharField(
        max_length=20,
        choices=Scope.choices,
    )

    params = models.JSONField(default=dict)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = [
            "name",
            "id",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "employee",
                    "scope",
                    "name",
                ],
                name="backlog_unique_saved_filter_name",
            ),
        ]

    def __str__(self):
        return (
            f"{self.employee} · "
            f"{self.get_scope_display()} · "
            f"{self.name}"
        )


class TaskWatcher(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="watcher_links",
    )

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="task_watcher_links",
    )

    added_by = models.ForeignKey(
        Employee,
        on_delete=models.SET_NULL,
        related_name="added_task_watchers",
        null=True,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "employee__display_name",
            "employee__username",
            "id",
        ]

        constraints = [
            models.UniqueConstraint(
                fields=[
                    "task",
                    "employee",
                ],
                name="backlog_unique_task_watcher",
            ),
        ]

    def __str__(self):
        return (
            f"{self.task.code} · "
            f"{self.employee}"
        )


class TaskComment(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    author = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="task_comments",
    )

    body = models.TextField()

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "created_at",
            "id",
        ]

    def __str__(self):
        return (
            f"{self.task.code} · "
            f"{self.author} · "
            f"{self.created_at:%d.%m.%Y %H:%M}"
        )


class TelegramOutbox(models.Model):
    class EventType(models.TextChoices):
        ASSIGNED = "assigned", "Назначена"
        STATUS_CHANGED = "status_changed", "Изменён статус"
        COMPLETED = "completed", "Завершена"
        OVERDUE = "overdue", "Просрочена"
        COMMENTED = "commented", "Новый комментарий"

    recipient = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="telegram_outbox",
    )

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="telegram_outbox",
    )

    event_type = models.CharField(
        max_length=30,
        choices=EventType.choices,
    )

    dedupe_key = models.CharField(
        max_length=255,
        unique=True,
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    available_at = models.DateTimeField(
        default=timezone.now,
    )

    sent_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    attempts = models.PositiveIntegerField(
        default=0,
    )

    last_error = models.TextField(
        blank=True,
    )

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(
                fields=["sent_at", "available_at"],
                name="tg_outbox_pending_idx",
            ),
        ]


class TelegramLinkRequest(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,
        related_name="telegram_link_requests",
    )

    token_hash = models.CharField(
        max_length=64,
        unique=True,
    )

    telegram_user_id = models.BigIntegerField()
    telegram_chat_id = models.BigIntegerField()

    telegram_username = models.CharField(
        max_length=100,
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    expires_at = models.DateTimeField()

    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_consumed(self):
        return self.consumed_at is not None

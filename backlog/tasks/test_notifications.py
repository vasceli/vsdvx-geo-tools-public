from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from tasks.models import (
    Employee,
    Task,
    TaskComment,
    TaskWatcher,
    TelegramOutbox,
)
from tasks.notifications import (
    deliver_pending_outbox,
    enqueue_assignment,
    enqueue_comment,
    enqueue_completion,
    enqueue_overdue_tasks,
    enqueue_status_change,
)


class TelegramNotificationTests(TestCase):
    def setUp(self):
        self.reporter = Employee.objects.create(
            username="reporter",
            display_name="Постановщик",
            telegram_chat_id=1001,
            telegram_user_id=2001,
        )

        self.assignee = Employee.objects.create(
            username="assignee",
            display_name="Исполнитель",
            telegram_chat_id=1002,
            telegram_user_id=2002,
        )

        self.manager = Employee.objects.create(
            username="manager-test",
            display_name="Руководитель тест",
        )

        self.task = Task.objects.create(
            code="TASK-900",
            title="Тест Telegram",
            created_by=self.reporter,
            reporter_employee=self.reporter,
            reporter="Постановщик",
        )

    def test_assignment_notifies_assignee_only(self):
        self.task.assignee = self.assignee
        self.task.save()

        count = enqueue_assignment(
            task=self.task,
            actor=self.manager,
            previous_assignee_id=None,
        )

        self.assertEqual(count, 1)

        recipients = set(
            TelegramOutbox.objects.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipients,
            {
                self.assignee.pk,
            },
        )

    def test_status_change_does_not_notify_actor(self):
        self.task.assignee = self.assignee
        self.task.status = Task.Status.IN_PROGRESS
        self.task.save()

        count = enqueue_status_change(
            task=self.task,
            actor=self.assignee,
            old_status=Task.Status.NEW,
        )

        self.assertEqual(count, 1)

        item = TelegramOutbox.objects.get()

        self.assertEqual(
            item.recipient_id,
            self.reporter.pk,
        )

    def test_completion_notifies_other_participant(self):
        self.task.assignee = self.assignee
        self.task.status = Task.Status.DONE
        self.task.completion_comment = "Готово."
        self.task.completed_at = timezone.now()
        self.task.save()

        count = enqueue_completion(
            task=self.task,
            actor=self.assignee,
            old_status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(count, 1)

        item = TelegramOutbox.objects.get()

        self.assertEqual(
            item.recipient_id,
            self.reporter.pk,
        )

    def test_overdue_is_enqueued_only_once_per_deadline(self):
        due = timezone.now() - timedelta(minutes=10)

        self.task.assignee = self.assignee
        self.task.due_at = due
        self.task.save()

        first = enqueue_overdue_tasks()
        second = enqueue_overdue_tasks()

        self.assertEqual(first, 2)
        self.assertEqual(second, 0)
        self.assertEqual(
            TelegramOutbox.objects.count(),
            2,
        )

    def test_status_change_notifies_watcher(self):
        watcher = Employee.objects.create(
            username="watcher-notify",
            display_name="Наблюдатель",
            telegram_chat_id=1010,
            telegram_user_id=2010,
        )

        TaskWatcher.objects.create(
            task=self.task,
            employee=watcher,
            added_by=self.manager,
        )

        self.task.status = Task.Status.IN_PROGRESS
        self.task.save()

        count = enqueue_status_change(
            task=self.task,
            actor=self.manager,
            old_status=Task.Status.NEW,
        )

        self.assertEqual(count, 2)

        recipients = set(
            TelegramOutbox.objects.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipients,
            {
                self.reporter.pk,
                watcher.pk,
            },
        )

    def test_watcher_is_not_duplicated_with_assignee(self):
        self.task.assignee = self.assignee
        self.task.status = Task.Status.IN_PROGRESS
        self.task.save()

        TaskWatcher.objects.create(
            task=self.task,
            employee=self.assignee,
            added_by=self.manager,
        )

        count = enqueue_status_change(
            task=self.task,
            actor=self.manager,
            old_status=Task.Status.NEW,
        )

        recipients = list(
            TelegramOutbox.objects.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(count, 2)
        self.assertEqual(
            recipients.count(self.assignee.pk),
            1,
        )

    def test_assignment_notifies_watcher(self):
        watcher = Employee.objects.create(
            username="assignment-watcher",
            display_name="Наблюдатель назначения",
            telegram_chat_id=1011,
            telegram_user_id=2011,
        )

        TaskWatcher.objects.create(
            task=self.task,
            employee=watcher,
            added_by=self.manager,
        )

        self.task.assignee = self.assignee
        self.task.save()

        count = enqueue_assignment(
            task=self.task,
            actor=self.manager,
            previous_assignee_id=None,
        )

        self.assertEqual(count, 2)

        self.assertTrue(
            TelegramOutbox.objects.filter(
                recipient=watcher,
                event_type=TelegramOutbox.EventType.ASSIGNED,
            ).exists()
        )

    def test_comment_notifies_participants_and_watcher(self):
        watcher = Employee.objects.create(
            username="comment-watcher",
            display_name="Наблюдатель комментария",
            telegram_chat_id=1012,
            telegram_user_id=2012,
        )

        TaskWatcher.objects.create(
            task=self.task,
            employee=watcher,
            added_by=self.manager,
        )

        self.task.assignee = self.assignee
        self.task.save()

        comment = TaskComment.objects.create(
            task=self.task,
            author=self.manager,
            body="Проверить новый комментарий",
        )

        count = enqueue_comment(
            task=self.task,
            actor=self.manager,
            comment=comment,
        )

        self.assertEqual(count, 3)

        recipients = set(
            TelegramOutbox.objects.values_list(
                "recipient_id",
                flat=True,
            )
        )

        self.assertEqual(
            recipients,
            {
                self.reporter.pk,
                self.assignee.pk,
                watcher.pk,
            },
        )

    def test_comment_does_not_notify_author(self):
        TaskWatcher.objects.create(
            task=self.task,
            employee=self.reporter,
            added_by=self.manager,
        )

        comment = TaskComment.objects.create(
            task=self.task,
            author=self.reporter,
            body="Мой комментарий",
        )

        count = enqueue_comment(
            task=self.task,
            actor=self.reporter,
            comment=comment,
        )

        self.assertEqual(count, 0)
        self.assertEqual(
            TelegramOutbox.objects.count(),
            0,
        )

    @patch.dict(
        "os.environ",
        {"BACKLOG_BASE_URL": "https://backlog.example.com"},
        clear=False,
    )
    @patch("tasks.notifications.send_message")
    def test_outbox_delivery_marks_message_sent(
        self,
        send_message,
    ):
        self.task.assignee = self.assignee
        self.task.save()

        enqueue_assignment(
            task=self.task,
            actor=self.manager,
            previous_assignee_id=None,
        )

        sent, failed = deliver_pending_outbox()

        self.assertEqual(sent, 1)
        self.assertEqual(failed, 0)

        self.assertEqual(
            TelegramOutbox.objects.filter(
                sent_at__isnull=False,
            ).count(),
            1,
        )

    @patch.dict(
        "os.environ",
        {"BACKLOG_BASE_URL": "https://backlog.example.com"},
        clear=False,
    )
    @patch(
        "tasks.notifications.send_message",
        side_effect=RuntimeError("telegram unavailable"),
    )
    def test_failed_delivery_is_retried(
        self,
        send_message,
    ):
        self.task.assignee = self.assignee
        self.task.reporter_employee = None
        self.task.save()

        enqueue_assignment(
            task=self.task,
            actor=self.manager,
            previous_assignee_id=None,
        )

        sent, failed = deliver_pending_outbox()

        self.assertEqual(sent, 0)
        self.assertEqual(failed, 1)

        item = TelegramOutbox.objects.get()

        self.assertIsNone(item.sent_at)
        self.assertEqual(item.attempts, 1)
        self.assertGreater(
            item.available_at,
            timezone.now(),
        )

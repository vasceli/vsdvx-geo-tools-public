from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class TaskReopenTests(TestCase):
    def setUp(self):
        self.worker = Employee.objects.create(
            username="reopen-worker",
            display_name="Reopen Worker",
        )

        self.other = Employee.objects.create(
            username="reopen-other",
            display_name="Reopen Other",
        )

        self.manager = Employee.objects.create(
            username="reopen-manager",
            display_name="Reopen Manager",
            role=Employee.Role.MANAGER,
        )

        now = timezone.now()

        self.task = Task.objects.create(
            code="REOPEN-001",
            title="Completed task",
            created_by=self.worker,
            assignee=self.worker,
            priority=Task.Priority.P1,
            status=Task.Status.DONE,
            started_at=now - timedelta(days=2),
            completed_at=now,
            completion_comment="Первоначальный результат",
            completion_url="https://example.com/old-result",
        )

    def post_reopen(
        self,
        *,
        user,
        status=Task.Status.IN_PROGRESS,
    ):
        return self.client.post(
            f"/tasks/{self.task.pk}/reopen/",
            {
                "status": status,
            },
            HTTP_X_AUTH_USER=user.username,
        )

    def test_assignee_can_reopen_to_in_progress(self):
        started_at = self.task.started_at
        task_pk = self.task.pk
        task_count = Task.objects.count()

        response = self.post_reopen(
            user=self.worker,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(self.task.pk, task_pk)
        self.assertEqual(Task.objects.count(), task_count)
        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )
        self.assertIsNone(self.task.completed_at)

        self.assertEqual(
            self.task.started_at,
            started_at,
        )

        self.assertEqual(
            self.task.completion_comment,
            "Первоначальный результат",
        )

        self.assertEqual(
            self.task.completion_url,
            "https://example.com/old-result",
        )

    def test_can_reopen_to_new(self):
        response = self.post_reopen(
            user=self.worker,
            status=Task.Status.NEW,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.NEW,
        )

        self.assertIsNone(self.task.completed_at)

    def test_reopen_is_written_to_history(self):
        self.post_reopen(
            user=self.worker,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="status",
                old_value=Task.Status.DONE,
                new_value=Task.Status.IN_PROGRESS,
            ).exists()
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="completed_at",
            ).exists()
        )

    def test_other_employee_cannot_reopen(self):
        response = self.post_reopen(
            user=self.other,
        )

        self.assertEqual(response.status_code, 403)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )

        self.assertIsNotNone(self.task.completed_at)

    def test_manager_can_reopen_other_employee_task(self):
        response = self.post_reopen(
            user=self.manager,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )

    def test_cancelled_task_is_not_reopened(self):
        self.task.status = Task.Status.CANCELLED
        self.task.save()

        response = self.post_reopen(
            user=self.worker,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.CANCELLED,
        )

    def test_get_does_not_reopen_task(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/reopen/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )

    def test_reopened_task_shows_previous_result(self):
        self.post_reopen(
            user=self.worker,
        )

        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Предыдущий результат завершения",
        )

        self.assertContains(
            response,
            "Первоначальный результат",
        )

        self.assertContains(
            response,
            "https://example.com/old-result",
        )

    def test_invalid_status_does_not_reopen(self):
        response = self.post_reopen(
            user=self.worker,
            status=Task.Status.CANCELLED,
        )

        self.assertEqual(response.status_code, 400)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )

        self.assertIsNotNone(self.task.completed_at)

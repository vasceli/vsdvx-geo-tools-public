from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class QuickActionsTests(TestCase):
    def setUp(self):
        self.worker = Employee.objects.create(
            username="quick-worker",
            display_name="Quick Worker",
        )

        self.other = Employee.objects.create(
            username="quick-other",
            display_name="Quick Other",
        )

        self.manager = Employee.objects.create(
            username="quick-manager",
            display_name="Quick Manager",
            role=Employee.Role.MANAGER,
        )

        self.task = Task.objects.create(
            code="QUICK-001",
            title="Quick action task",
            created_by=self.worker,
            assignee=self.worker,
            priority=Task.Priority.P1,
            status=Task.Status.NEW,
        )

    def quick(
        self,
        *,
        user,
        status,
        next_url="/",
    ):
        return self.client.post(
            f"/tasks/{self.task.pk}/quick-status/",
            {
                "status": status,
                "next": next_url,
            },
            HTTP_X_AUTH_USER=user.username,
        )

    def test_quick_start_sets_started_at(self):
        response = self.quick(
            user=self.worker,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/")

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )

        self.assertIsNotNone(
            self.task.started_at,
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="status",
                old_value=Task.Status.NEW,
                new_value=Task.Status.IN_PROGRESS,
            ).exists()
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="started_at",
            ).exists()
        )

    def test_quick_start_does_not_reset_started_at(self):
        started_at = timezone.now() - timedelta(days=3)

        self.task.status = Task.Status.REVIEW
        self.task.started_at = started_at
        self.task.save()

        response = self.quick(
            user=self.worker,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.started_at,
            started_at,
        )

    def test_quick_review_from_in_progress(self):
        self.task.status = Task.Status.IN_PROGRESS
        self.task.started_at = timezone.now()
        self.task.save()

        response = self.quick(
            user=self.worker,
            status=Task.Status.REVIEW,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.REVIEW,
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="status",
                old_value=Task.Status.IN_PROGRESS,
                new_value=Task.Status.REVIEW,
            ).exists()
        )

    def test_review_from_new_is_rejected(self):
        response = self.quick(
            user=self.worker,
            status=Task.Status.REVIEW,
        )

        self.assertEqual(response.status_code, 400)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.NEW,
        )

    def test_other_employee_cannot_use_quick_action(self):
        response = self.quick(
            user=self.other,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 403)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.NEW,
        )

    def test_manager_can_use_quick_action(self):
        response = self.quick(
            user=self.manager,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )

    def test_terminal_task_is_not_changed(self):
        self.task.status = Task.Status.DONE
        self.task.completed_at = timezone.now()
        self.task.save()

        response = self.quick(
            user=self.worker,
            status=Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )

        self.assertIsNotNone(
            self.task.completed_at,
        )

    def test_get_does_not_change_status(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/quick-status/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.NEW,
        )

    def test_home_shows_quick_actions(self):
        response = self.client.get(
            "/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "В работу",
        )

        self.assertContains(
            response,
            "Завершить",
        )

        self.assertNotContains(
            response,
            "На проверку",
        )

    def test_home_shows_review_action_when_in_progress(self):
        self.task.status = Task.Status.IN_PROGRESS
        self.task.started_at = timezone.now()
        self.task.save()

        response = self.client.get(
            "/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "На проверку",
        )

    def test_complete_query_opens_completion_dialog(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/?complete=1",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            'getElementById("completion-dialog").showModal()',
        )

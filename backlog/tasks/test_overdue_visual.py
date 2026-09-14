from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class OverdueVisualTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="overdue-worker",
            display_name="Overdue Worker",
        )

        self.now = timezone.now().replace(
            second=0,
            microsecond=0,
        )

        self.task = Task.objects.create(
            code="OVERDUE-001",
            title="Overdue task",
            created_by=self.employee,
            assignee=self.employee,
            priority=Task.Priority.P1,
            status=Task.Status.IN_PROGRESS,
            started_at=self.now - timedelta(days=4),
            due_at=self.now - timedelta(
                days=3,
                hours=2,
            ),
        )

    def test_active_task_is_overdue(self):
        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertTrue(
                self.task.is_overdue
            )

    def test_future_task_is_not_overdue(self):
        self.task.due_at = (
            self.now + timedelta(hours=2)
        )

        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertFalse(
                self.task.is_overdue
            )

    def test_done_task_is_not_overdue(self):
        self.task.status = Task.Status.DONE
        self.task.completed_at = self.now
        self.task.save()

        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertFalse(
                self.task.is_overdue
            )

    def test_cancelled_task_is_not_overdue(self):
        self.task.status = Task.Status.CANCELLED
        self.task.save()

        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertFalse(
                self.task.is_overdue
            )

    def test_overdue_display_days(self):
        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertEqual(
                self.task.overdue_display,
                "Просрочено 3 дня 2 ч.",
            )

    def test_overdue_display_hours(self):
        self.task.due_at = (
            self.now
            - timedelta(
                hours=5,
                minutes=17,
            )
        )

        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            self.assertEqual(
                self.task.overdue_display,
                "Просрочено 5 ч. 17 мин.",
            )

    def test_home_shows_overdue_visual(self):
        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            response = self.client.get(
                "/",
                HTTP_X_AUTH_USER=self.employee.username,
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Просрочено 3 дня 2 ч.",
        )

        self.assertContains(
            response,
            "task-overdue",
        )

        self.assertContains(
            response,
            "deadline-overdue",
        )

    def test_detail_shows_overdue_visual(self):
        with patch(
            "tasks.models.timezone.now",
            return_value=self.now,
        ):
            response = self.client.get(
                f"/tasks/{self.task.pk}/",
                HTTP_X_AUTH_USER=self.employee.username,
            )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.assertContains(
            response,
            "Просрочено 3 дня 2 ч.",
        )

        self.assertContains(
            response,
            "deadline-detail-overdue",
        )

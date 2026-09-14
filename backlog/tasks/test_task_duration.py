from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class TaskDurationTests(TestCase):
    def setUp(self):
        self.worker = Employee.objects.create(
            username="duration-worker",
            display_name="Duration Worker",
        )

    def make_task(self, **kwargs):
        defaults = {
            "code": "DURATION-001",
            "title": "Duration test task",
            "created_by": self.worker,
            "assignee": self.worker,
            "priority": Task.Priority.P1,
            "status": Task.Status.NEW,
        }
        defaults.update(kwargs)

        return Task.objects.create(**defaults)

    def edit(self, task, status):
        return self.client.post(
            f"/tasks/{task.pk}/edit/",
            {
                "status": status,
                "next_step": "",
                "blockers": "",
                "materials_url": "",
                "comment": "",
            },
            HTTP_X_AUTH_USER=self.worker.username,
        )

    def test_first_in_progress_transition_sets_started_at(self):
        task = self.make_task()

        response = self.edit(
            task,
            Task.Status.IN_PROGRESS,
        )

        self.assertEqual(response.status_code, 302)

        task.refresh_from_db()

        self.assertIsNotNone(task.started_at)

        self.assertTrue(
            task.history.filter(
                field_name="started_at",
            ).exists()
        )

    def test_started_at_is_not_reset(self):
        task = self.make_task()

        self.edit(
            task,
            Task.Status.IN_PROGRESS,
        )

        task.refresh_from_db()
        first_started_at = task.started_at

        self.edit(
            task,
            Task.Status.IN_PROGRESS,
        )

        task.refresh_from_db()

        self.assertEqual(
            task.started_at,
            first_started_at,
        )

    def test_duration_properties(self):
        completed_at = timezone.now()

        task = self.make_task(
            status=Task.Status.DONE,
            started_at=completed_at - timedelta(
                days=1,
                hours=3,
            ),
            completed_at=completed_at,
        )

        created_at = completed_at - timedelta(
            days=2,
            hours=3,
        )

        Task.objects.filter(
            pk=task.pk,
        ).update(
            created_at=created_at,
        )

        task.refresh_from_db()

        self.assertEqual(
            task.total_duration_display,
            "2 дн. 3 ч.",
        )

        self.assertEqual(
            task.work_duration_display,
            "1 дн. 3 ч.",
        )

    def test_done_pool_shows_durations(self):
        completed_at = timezone.now()

        task = self.make_task(
            status=Task.Status.DONE,
            started_at=completed_at - timedelta(hours=5),
            completed_at=completed_at,
            completion_comment="Готово",
        )

        Task.objects.filter(
            pk=task.pk,
        ).update(
            created_at=completed_at - timedelta(hours=8),
        )

        response = self.client.get(
            "/tasks/done/",
            HTTP_X_AUTH_USER=self.worker.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Общий срок:",
        )

        self.assertContains(
            response,
            "8 ч.",
        )

        self.assertContains(
            response,
            "В работе:",
        )

        self.assertContains(
            response,
            "5 ч.",
        )

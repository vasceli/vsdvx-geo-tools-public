from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class DoneTasksTests(TestCase):
    def setUp(self):
        self.worker = Employee.objects.create(
            username="worker",
            display_name="Worker",
        )
        self.other = Employee.objects.create(
            username="other",
            display_name="Other",
        )

        now = timezone.now()

        self.done = Task.objects.create(
            code="DONE-001",
            title="Piter Dent report",
            reporter="Василий",
            direction="Отчётность",
            created_by=self.worker,
            assignee=self.worker,
            priority=Task.Priority.P1,
            status=Task.Status.DONE,
            completion_comment="Подготовлен итоговый отчёт для клиента",
            completion_url="https://example.com/result",
            completed_at=now - timedelta(days=2),
        )

        self.done_other = Task.objects.create(
            code="DONE-002",
            title="Other completed task",
            direction="Продление",
            created_by=self.other,
            assignee=self.other,
            priority=Task.Priority.P2,
            status=Task.Status.DONE,
            completion_comment="Продление согласовано",
            completed_at=now - timedelta(days=10),
        )

        Task.objects.create(
            code="OPEN-001",
            title="Open task",
            created_by=self.worker,
            assignee=self.worker,
            priority=Task.Priority.P1,
            status=Task.Status.IN_PROGRESS,
        )

        Task.objects.create(
            code="CANCEL-001",
            title="Cancelled task",
            created_by=self.worker,
            assignee=self.worker,
            priority=Task.Priority.P1,
            status=Task.Status.CANCELLED,
            completed_at=now,
        )

    def get(self, params=None):
        return self.client.get(
            "/tasks/done/",
            params or {},
            HTTP_X_AUTH_USER="worker",
        )

    def test_shows_only_done_tasks(self):
        response = self.get()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Piter Dent report")
        self.assertContains(response, "Other completed task")
        self.assertNotContains(response, "Open task")
        self.assertNotContains(response, "Cancelled task")

    def test_shows_result_and_result_url(self):
        response = self.get()

        self.assertContains(
            response,
            "Подготовлен итоговый отчёт для клиента",
        )
        self.assertContains(response, "https://example.com/result")

    def test_searches_completion_result(self):
        response = self.get({"q": "итоговый отчёт"})

        self.assertContains(response, "Piter Dent report")
        self.assertNotContains(response, "Other completed task")

    def test_filters_by_assignee(self):
        response = self.get({
            "assignee": str(self.worker.pk),
        })

        self.assertContains(response, "Piter Dent report")
        self.assertNotContains(response, "Other completed task")

    def test_filters_by_direction(self):
        response = self.get({
            "direction": "Отчётность",
        })

        self.assertContains(response, "Piter Dent report")
        self.assertNotContains(response, "Other completed task")

    def test_filters_by_priority(self):
        response = self.get({
            "priority": Task.Priority.P2,
        })

        self.assertNotContains(response, "Piter Dent report")
        self.assertContains(response, "Other completed task")

    def test_filters_by_completion_period(self):
        today = timezone.localdate()

        response = self.get({
            "completed_from": (today - timedelta(days=5)).isoformat(),
            "completed_to": today.isoformat(),
        })

        self.assertContains(response, "Piter Dent report")
        self.assertNotContains(response, "Other completed task")

    def test_newest_completed_task_is_first(self):
        response = self.get()
        content = response.content.decode()

        self.assertLess(
            content.index("Piter Dent report"),
            content.index("Other completed task"),
        )

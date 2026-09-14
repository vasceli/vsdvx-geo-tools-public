from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class MyTasksFiltersTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="worker",
            display_name="Worker",
        )

        self.other = Employee.objects.create(
            username="other",
            display_name="Other",
        )

        self.alpha = Task.objects.create(
            code="TASK-201",
            title="Alpha client",
            reporter="Лера",
            direction="Продление",
            created_by=self.employee,
            assignee=self.employee,
            priority=Task.Priority.P1,
            status=Task.Status.NEW,
            due_at=timezone.now() - timedelta(days=1),
        )

        self.beta = Task.objects.create(
            code="TASK-202",
            title="Beta project",
            reporter="Оля",
            direction="Операционка",
            created_by=self.employee,
            assignee=self.employee,
            priority=Task.Priority.P2,
            status=Task.Status.IN_PROGRESS,
            due_at=timezone.now() + timedelta(days=2),
        )

        Task.objects.create(
            code="TASK-203",
            title="Other employee task",
            created_by=self.other,
            assignee=self.other,
        )

        self.review = Task.objects.create(
            code="TASK-204",
            title="Review task",
            reporter="Лера",
            direction="Операционка",
            created_by=self.employee,
            assignee=self.employee,
            priority=Task.Priority.P2,
            status=Task.Status.REVIEW,
            due_at=timezone.now() + timedelta(days=3),
        )

    def get(self, params=None):
        return self.client.get(
            "/",
            params or {},
            HTTP_X_AUTH_USER="worker",
        )

    def test_searches_only_my_tasks(self):
        response = self.get({"q": "Alpha"})

        self.assertContains(response, "Alpha client")
        self.assertNotContains(response, "Beta project")
        self.assertNotContains(response, "Other employee task")

    def test_filters_by_status(self):
        response = self.get({
            "status": Task.Status.IN_PROGRESS,
        })

        self.assertContains(response, "Beta project")
        self.assertNotContains(response, "Alpha client")

    def test_filters_by_priority(self):
        response = self.get({
            "priority": Task.Priority.P1,
        })

        self.assertContains(response, "Alpha client")
        self.assertNotContains(response, "Beta project")

    def test_filters_by_direction(self):
        response = self.get({
            "direction": "Продление",
        })

        self.assertContains(response, "Alpha client")
        self.assertNotContains(response, "Beta project")

    def test_filters_overdue_tasks(self):
        response = self.get({
            "overdue": "1",
        })

        self.assertContains(response, "Alpha client")
        self.assertNotContains(response, "Beta project")

    def test_hides_review_tasks(self):
        response = self.get({
            "hide_review": "1",
        })

        self.assertNotContains(response, "Review task")
        self.assertContains(response, "Alpha client")
        self.assertContains(response, "Beta project")

    def test_sorts_by_title(self):
        response = self.get({
            "sort": "title",
        })

        content = response.content.decode()

        self.assertLess(
            content.index("Alpha client"),
            content.index("Beta project"),
        )

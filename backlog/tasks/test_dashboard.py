from datetime import datetime, timedelta

from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task


class EmployeeDashboardTests(TestCase):
    def setUp(self):
        self.manager = Employee.objects.create(
            username="manager",
            display_name="Руководитель",
            role=Employee.Role.MANAGER,
        )

        self.admin = Employee.objects.create(
            username="admin",
            display_name="admin",
        )

        self.member = Employee.objects.create(
            username="member",
            display_name="Сотрудник",
        )

        self.other = Employee.objects.create(
            username="other",
            display_name="Другой",
        )

        self.mark = Employee.objects.create(
            username="mark",
            display_name="Марк",
        )

        now = timezone.now()

        self.open_task = Task.objects.create(
            code="TASK-D01",
            title="Просроченная P0",
            created_by=self.manager,
            assignee=self.member,
            priority=Task.Priority.P0,
            status=Task.Status.IN_PROGRESS,
            due_at=now - timedelta(days=1),
        )

        self.review_task = Task.objects.create(
            code="TASK-D02",
            title="P1 на проверке",
            created_by=self.manager,
            assignee=self.other,
            priority=Task.Priority.P1,
            status=Task.Status.REVIEW,
        )

        self.unassigned_task = Task.objects.create(
            code="TASK-D03",
            title="Без исполнителя",
            created_by=self.manager,
            priority=Task.Priority.P2,
            status=Task.Status.NEW,
        )

        self.done_task = Task.objects.create(
            code="TASK-D04",
            title="Недавно завершённая",
            created_by=self.manager,
            assignee=self.member,
            priority=Task.Priority.P2,
            status=Task.Status.DONE,
            started_at=now - timedelta(hours=4),
            completed_at=now - timedelta(hours=2),
        )

    def headers(self, employee):
        return {
            "HTTP_X_AUTH_USER": employee.username,
        }

    def test_regular_employee_cannot_open_dashboard(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.member),
        )

        self.assertEqual(response.status_code, 403)

    def test_manager_can_open_dashboard(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.manager),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Дашборд сотрудников",
        )

    def test_system_admin_can_open_dashboard(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.admin),
        )

        self.assertEqual(response.status_code, 200)

    def test_team_metrics_are_correct(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.manager),
        )

        team = response.context["team"]

        self.assertEqual(team["total"], 4)
        self.assertEqual(team["open"], 3)
        self.assertEqual(team["in_progress"], 1)
        self.assertEqual(team["review"], 1)
        self.assertEqual(team["overdue"], 1)
        self.assertEqual(team["high_priority"], 2)
        self.assertEqual(team["done_7"], 1)
        self.assertEqual(team["done_30"], 1)
        self.assertEqual(team["unassigned"], 1)

    def test_admin_is_not_in_employee_statistics(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.manager),
        )

        usernames = {
            row["employee"].username
            for row in response.context["employee_rows"]
        }

        self.assertNotIn("admin", usernames)
        self.assertNotIn("mark", usernames)
        self.assertIn("manager", usernames)
        self.assertIn("member", usernames)
        self.assertIn("other", usernames)

    def test_average_work_duration_is_calculated(self):
        response = self.client.get(
            "/dashboard/",
            **self.headers(self.manager),
        )

        member_row = next(
            row
            for row in response.context["employee_rows"]
            if row["employee"] == self.member
        )

        self.assertEqual(
            member_row["avg_work"],
            "2 ч.",
        )
        self.assertEqual(
            member_row["avg_work_sample"],
            1,
        )

    def test_old_work_duration_is_ignored(self):
        cutoff = timezone.make_aware(
            datetime(
                2026,
                8,
                18,
                0,
                0,
            ),
            timezone.get_current_timezone(),
        )

        Task.objects.create(
            code="TASK-D05",
            title="Старая задача с кривым временем",
            created_by=self.manager,
            assignee=self.member,
            priority=Task.Priority.P2,
            status=Task.Status.DONE,
            started_at=cutoff - timedelta(days=3),
            completed_at=cutoff - timedelta(days=2),
        )

        response = self.client.get(
            "/dashboard/",
            **self.headers(self.manager),
        )

        member_row = next(
            row
            for row in response.context["employee_rows"]
            if row["employee"] == self.member
        )

        self.assertEqual(
            member_row["avg_work_sample"],
            1,
        )

    def test_member_does_not_see_dashboard_navigation(self):
        response = self.client.get(
            "/",
            **self.headers(self.member),
        )

        self.assertNotContains(
            response,
            'href="/dashboard/"',
            html=False,
        )

    def test_manager_and_admin_see_dashboard_navigation(self):
        for employee in [
            self.manager,
            self.admin,
        ]:
            with self.subTest(
                employee=employee.username,
            ):
                response = self.client.get(
                    "/",
                    **self.headers(employee),
                )

                self.assertContains(
                    response,
                    'href="/dashboard/"',
                    html=False,
                )

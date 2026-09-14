from django.test import TestCase

from tasks.models import Employee, Task


class SystemAdminPermissionTests(TestCase):
    def setUp(self):
        self.admin = Employee.objects.create(
            username="admin",
            display_name="Admin",
            role=Employee.Role.MEMBER,
        )

        self.worker = Employee.objects.create(
            username="worker-admin-test",
            display_name="Worker",
            role=Employee.Role.MEMBER,
        )

        self.task = Task.objects.create(
            code="TASK-990",
            title="Чужая задача",
            created_by=self.worker,
            reporter_employee=self.worker,
            reporter="Worker",
            assignee=self.worker,
            priority=Task.Priority.P2,
            status=Task.Status.NEW,
        )

        self.headers = {
            "HTTP_X_AUTH_USER": "admin",
        }

    def test_admin_is_not_business_manager(self):
        self.assertFalse(self.admin.is_manager)
        self.assertTrue(self.admin.is_system_admin)
        self.assertTrue(self.admin.can_manage_tasks)

    def test_admin_can_open_waiting_queue(self):
        response = self.client.get(
            "/tasks/waiting/",
            **self.headers,
        )

        self.assertEqual(response.status_code, 200)

    def test_admin_can_fully_edit_foreign_task(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/edit/",
            {
                "title": "Изменено администратором",
                "acceptance_criteria": "Новые критерии",
                "reporter": "Worker",
                "direction": "IT / процессы",
                "assignee": self.worker.pk,
                "priority": Task.Priority.P0,
                "status": Task.Status.IN_PROGRESS,
                "due_at": "",
                "estimate_hours": "2",
                "blockers": "",
                "next_step": "Продолжить",
                "materials_url": "",
                "comment": "admin edit",
            },
            **self.headers,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.title,
            "Изменено администратором",
        )
        self.assertEqual(
            self.task.priority,
            Task.Priority.P0,
        )
        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )

    def test_admin_can_complete_foreign_task(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/complete/",
            {
                "status": Task.Status.DONE,
                "result": "Закрыто администратором",
                "result_url": "",
            },
            **self.headers,
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )
        self.assertEqual(
            self.task.completion_comment,
            "Закрыто администратором",
        )

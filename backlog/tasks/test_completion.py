from django.test import TestCase

from .models import Employee, Task


class TaskCompletionTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="worker",
            display_name="Worker",
        )

        self.other = Employee.objects.create(
            username="other",
            display_name="Other",
        )

        self.task = Task.objects.create(
            code="TASK-998",
            title="Completion workflow test",
            created_by=self.employee,
            assignee=self.employee,
        )

    def test_assignee_can_complete_task(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/complete/",
            {
                "status": Task.Status.DONE,
                "result": "Работа выполнена",
                "result_url": "https://drive.google.com/example",
            },
            HTTP_X_AUTH_USER="worker",
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            Task.Status.DONE,
        )

        self.assertEqual(
            self.task.completion_comment,
            "Работа выполнена",
        )

        self.assertEqual(
            self.task.completion_url,
            "https://drive.google.com/example",
        )

        self.assertIsNotNone(
            self.task.completed_at,
        )

    def test_result_is_required(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/complete/",
            {
                "status": Task.Status.DONE,
                "result": "",
                "result_url": "",
            },
            HTTP_X_AUTH_USER="worker",
        )

        self.assertEqual(response.status_code, 400)

        self.task.refresh_from_db()

        self.assertNotEqual(
            self.task.status,
            Task.Status.DONE,
        )

    def test_other_employee_cannot_complete_task(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/complete/",
            {
                "status": Task.Status.DONE,
                "result": "Не должен сохраниться",
            },
            HTTP_X_AUTH_USER="other",
        )

        self.assertEqual(response.status_code, 403)

    def test_detail_shows_completion_button_to_assignee(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER="worker",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Завершить задачу",
        )

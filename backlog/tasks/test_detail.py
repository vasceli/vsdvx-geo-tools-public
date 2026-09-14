from django.test import TestCase

from .models import Employee, Task


class TaskDetailViewTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="detail_test",
            display_name="Detail Test",
        )

        self.task = Task.objects.create(
            code="TASK-999",
            title="Detail page regression test",
            created_by=self.employee,
            assignee=self.employee,
        )

    def test_task_detail_renders(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER=self.employee.username,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "TASK-999")
        self.assertContains(
            response,
            "Detail page regression test",
        )

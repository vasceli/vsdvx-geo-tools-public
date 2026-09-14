from django.test import TestCase

from .models import Employee, Task


class IdentityMiddlewareTests(TestCase):
    def test_missing_identity_is_forbidden(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 403)

    def test_identity_creates_member(self):
        response = self.client.get(
            "/",
            HTTP_X_AUTH_USER="vasya",
        )

        self.assertEqual(response.status_code, 200)

        employee = Employee.objects.get(
            username="vasya",
        )

        self.assertEqual(
            employee.role,
            Employee.Role.MEMBER,
        )

    def test_healthcheck_does_not_require_identity(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")


class ManagerConstraintTests(TestCase):
    def test_multiple_managers_can_exist(self):
        first = Employee.objects.create(
            username="manager1",
            role=Employee.Role.MANAGER,
        )

        second = Employee.objects.create(
            username="manager2",
            role=Employee.Role.MANAGER,
        )

        self.assertTrue(first.can_manage_tasks)
        self.assertTrue(second.can_manage_tasks)


class TaskPermissionTests(TestCase):
    def setUp(self):
        self.manager = Employee.objects.create(
            username="manager",
            role=Employee.Role.MANAGER,
        )

        self.vasya = Employee.objects.create(
            username="vasya",
        )

        self.artem = Employee.objects.create(
            username="artem",
        )

        self.task = Task.objects.create(
            code="TASK-001",
            title="Test task",
            created_by=self.manager,
            assignee=self.vasya,
            priority=Task.Priority.P2,
            status=Task.Status.NEW,
        )

    def test_every_user_can_see_all_tasks(self):
        response = self.client.get(
            "/tasks/",
            HTTP_X_AUTH_USER="artem",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test task")

    def test_member_cannot_edit_another_users_task(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/edit/",
            HTTP_X_AUTH_USER="artem",
        )

        self.assertEqual(response.status_code, 403)

    def test_member_cannot_change_priority(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/edit/",
            {
                "status": Task.Status.IN_PROGRESS,
                "priority": Task.Priority.P0,
                "next_step": "Do work",
                "blockers": "",
                "materials_url": "",
                "comment": "",
            },
            HTTP_X_AUTH_USER="vasya",
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.priority,
            Task.Priority.P2,
        )

        self.assertEqual(
            self.task.status,
            Task.Status.IN_PROGRESS,
        )

    def test_manager_can_change_priority(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/edit/",
            {
                "title": self.task.title,
                "acceptance_criteria": "",
                "reporter": "",
                "direction": "IT / процессы",
                "assignee": self.vasya.pk,
                "priority": Task.Priority.P0,
                "status": Task.Status.IN_PROGRESS,
                "due_at": "",
                "estimate_hours": "",
                "blockers": "",
                "next_step": "",
                "materials_url": "",
                "comment": "",
            },
            HTTP_X_AUTH_USER="manager",
        )

        self.assertEqual(response.status_code, 302)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.priority,
            Task.Priority.P0,
        )

        self.assertTrue(
            self.task.history.filter(
                field_name="priority",
            ).exists()
        )

    def test_new_task_always_waits_for_manager_priority(self):
        response = self.client.post(
            "/tasks/new/",
            {
                "title": "New backlog item",
                "acceptance_criteria": "Done",
                "reporter": "Вася",
                "direction": "IT / процессы",
                "next_step": "",
                "materials_url": "",
                "comment": "",
            },
            HTTP_X_AUTH_USER="vasya",
        )

        self.assertEqual(response.status_code, 302)

        task = Task.objects.get(
            title="New backlog item",
        )

        self.assertEqual(
            task.priority,
            Task.Priority.WAITING,
        )


class BacklogImportTests(TestCase):
    CSV = """Бэклог задач
metadata

ID,Дата создания,Задача,Результат / критерий готовности,Кто поставил,Направление,Исполнитель,Приоритет Дмитрия,Статус,Срок,Оценка\\, ч,Зависимости / блокеры,Следующий шаг,Ссылка / материалы,Обновлено,Дата завершения,Комментарий
"""

    def make_csv(self):
        import csv
        import tempfile

        file = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".csv",
            delete=False,
        )

        writer = csv.writer(file)

        writer.writerow(["Бэклог задач"])
        writer.writerow(["metadata"])
        writer.writerow([])

        writer.writerow([
            "ID",
            "Дата создания",
            "Задача",
            "Результат / критерий готовности",
            "Кто поставил",
            "Направление",
            "Исполнитель",
            "Приоритет Дмитрия",
            "Статус",
            "Срок",
            "Оценка, ч",
            "Зависимости / блокеры",
            "Следующий шаг",
            "Ссылка / материалы",
            "Обновлено",
            "Дата завершения",
            "Комментарий",
        ])

        writer.writerow([
            "TASK-001",
            "05.08.2026",
            "Первая задача",
            "Готовый результат",
            "Лера",
            "Отчётность",
            "Василий",
            "P1 — высокий",
            "Новая",
            "06.08 до 12:00",
            "2",
            "",
            "Сделать",
            "",
            "05.08.2026",
            "",
            "Комментарий",
        ])

        writer.writerow([
            "TASK-002",
            "05.08.2026",
            "Вторая задача",
            "",
            "Оля",
            "Операционка",
            "Вася",
            "P2 — средний",
            "Готово",
            "07.08.2026",
            "",
            "",
            "",
            "",
            "",
            "07.08.2026",
            "",
        ])

        writer.writerow(["TASK-003"])

        file.close()
        return file.name

    def test_dry_run_rolls_back(self):
        from django.core.management import call_command

        path = self.make_csv()

        call_command(
            "import_backlog_csv",
            path,
            "--map-assignee",
            "Василий=vasiliy",
            "--map-assignee",
            "Вася=vasiliy",
            "--expected-count",
            "2",
            "--dry-run",
        )

        self.assertEqual(Task.objects.count(), 0)

    def test_import_preserves_rows_and_aliases(self):
        from django.core.management import call_command

        path = self.make_csv()

        call_command(
            "import_backlog_csv",
            path,
            "--map-assignee",
            "Василий=vasiliy",
            "--map-assignee",
            "Вася=vasiliy",
            "--expected-count",
            "2",
        )

        self.assertEqual(Task.objects.count(), 2)

        first = Task.objects.get(code="TASK-001")
        second = Task.objects.get(code="TASK-002")

        self.assertEqual(
            first.assignee.username,
            "vasiliy",
        )

        self.assertEqual(
            second.assignee.username,
            "vasiliy",
        )

        self.assertEqual(
            first.priority,
            Task.Priority.P1,
        )

        from django.utils import timezone

        self.assertEqual(
            timezone.localtime(first.due_at).hour,
            12,
        )

        self.assertEqual(
            first.source_data["Срок"],
            "06.08 до 12:00",
        )

    def test_unmapped_assignee_is_rejected(self):
        from django.core.management import CommandError, call_command

        path = self.make_csv()

        with self.assertRaises(CommandError):
            call_command(
                "import_backlog_csv",
                path,
                "--expected-count",
                "2",
            )

        self.assertEqual(Task.objects.count(), 0)

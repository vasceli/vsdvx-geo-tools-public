import importlib

from django.apps import apps
from django.test import TestCase

from .directions import (
    DIRECTIONS,
    DIRECTION_CHOICES,
)
from .forms import (
    ManagerTaskUpdateForm,
    MemberTaskUpdateForm,
    TaskCreateForm,
)
from .models import Employee, Task


class RussianTaskFormsTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="employee",
            display_name="Сотрудник",
        )

        self.manager = Employee.objects.create(
            username="manager",
            display_name="Руководитель",
            role=Employee.Role.MANAGER,
        )

        self.task = Task.objects.create(
            code="TASK-RU-1",
            title="Тест",
            created_by=self.manager,
            assignee=self.employee,
            direction="Операционка",
            priority=Task.Priority.P2,
            status=Task.Status.NEW,
        )

    def test_create_form_labels_are_russian(self):
        form = TaskCreateForm()

        expected = {
            "title": "Название",
            "acceptance_criteria": "Критерии готовности",
            "reporter": "Постановщик",
            "direction": "Направление",
            "next_step": "Следующий шаг",
            "materials_url": "Ссылка на материалы",
        }

        for field_name, label in expected.items():
            with self.subTest(field=field_name):
                self.assertEqual(
                    form.fields[field_name].label,
                    label,
                )

    def test_manager_edit_form_labels_are_russian(self):
        form = ManagerTaskUpdateForm(
            instance=self.task,
        )

        expected = {
            "title": "Название",
            "acceptance_criteria": "Критерии готовности",
            "reporter": "Постановщик",
            "direction": "Направление",
            "assignee": "Исполнитель",
            "priority": "Приоритет",
            "status": "Статус",
            "due_at": "Срок",
            "estimate_hours": "Оценка, часов",
            "blockers": "Блокеры",
            "next_step": "Следующий шаг",
            "materials_url": "Ссылка на материалы",
        }

        for field_name, label in expected.items():
            with self.subTest(field=field_name):
                self.assertEqual(
                    form.fields[field_name].label,
                    label,
                )

    def test_member_edit_form_labels_are_russian(self):
        form = MemberTaskUpdateForm(
            instance=self.task,
        )

        expected = {
            "status": "Статус",
            "next_step": "Следующий шаг",
            "blockers": "Блокеры",
            "materials_url": "Ссылка на материалы",
        }

        for field_name, label in expected.items():
            with self.subTest(field=field_name):
                self.assertEqual(
                    form.fields[field_name].label,
                    label,
                )

    def test_direction_choices_are_systematic(self):
        form = TaskCreateForm()

        self.assertEqual(
            tuple(form.fields["direction"].choices),
            DIRECTION_CHOICES,
        )

        self.assertIn(
            "Другое",
            DIRECTIONS,
        )

    def test_manager_direction_uses_same_choices(self):
        form = ManagerTaskUpdateForm(
            instance=self.task,
        )

        self.assertEqual(
            tuple(form.fields["direction"].choices),
            DIRECTION_CHOICES,
        )

    def test_create_rejects_arbitrary_direction(self):
        form = TaskCreateForm(
            data={
                "title": "Новая задача",
                "acceptance_criteria": "",
                "reporter": "Сотрудник",
                "direction": "Сам придумал направление",
                "next_step": "",
                "materials_url": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "direction",
            form.errors,
        )

    def test_create_requires_direction(self):
        form = TaskCreateForm(
            data={
                "title": "Новая задача",
                "acceptance_criteria": "",
                "reporter": "Сотрудник",
                "direction": "",
                "next_step": "",
                "materials_url": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "direction",
            form.errors,
        )

    def test_create_accepts_other_direction(self):
        form = TaskCreateForm(
            data={
                "title": "Новая задача",
                "acceptance_criteria": "",
                "reporter": "Сотрудник",
                "direction": "Другое",
                "next_step": "",
                "materials_url": "",
            }
        )

        self.assertTrue(
            form.is_valid(),
            form.errors,
        )

    def test_manager_edit_rejects_arbitrary_direction(self):
        form = ManagerTaskUpdateForm(
            instance=self.task,
            data={
                "title": self.task.title,
                "acceptance_criteria": "",
                "reporter": "",
                "direction": "Кривое направление",
                "assignee": self.employee.pk,
                "priority": Task.Priority.P2,
                "status": Task.Status.NEW,
                "due_at": "",
                "estimate_hours": "",
                "blockers": "",
                "next_step": "",
                "materials_url": "",
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "direction",
            form.errors,
        )

    def test_data_migration_normalizes_known_values(self):
        Task.objects.create(
            code="TASK-RU-2",
            title="Отчетность",
            created_by=self.manager,
            direction="Отчетность",
        )

        Task.objects.create(
            code="TASK-RU-3",
            title="Тест",
            created_by=self.manager,
            direction="тест",
        )

        Task.objects.create(
            code="TASK-RU-4",
            title="Оля",
            created_by=self.manager,
            direction="Оля",
        )

        blank_task = Task.objects.create(
            code="TASK-RU-5",
            title="Пустое",
            created_by=self.manager,
            direction="",
        )

        migration = importlib.import_module(
            "tasks.migrations."
            "0011_normalize_task_directions"
        )

        migration.normalize_task_directions(
            apps,
            None,
        )

        self.assertEqual(
            Task.objects.get(
                code="TASK-RU-2"
            ).direction,
            "Отчётность",
        )

        self.assertEqual(
            Task.objects.get(
                code="TASK-RU-3"
            ).direction,
            "Другое",
        )

        self.assertEqual(
            Task.objects.get(
                code="TASK-RU-4"
            ).direction,
            "Другое",
        )

        blank_task.refresh_from_db()

        self.assertEqual(
            blank_task.direction,
            "",
        )

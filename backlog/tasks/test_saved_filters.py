from django.test import TestCase

from .models import Employee, SavedTaskFilter, Task


class SavedTaskFilterTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="member",
            display_name="Сотрудник",
        )

        self.other = Employee.objects.create(
            username="other",
            display_name="Другой",
        )

        self.task = Task.objects.create(
            code="TASK-900",
            title="Просроченная P0",
            reporter="Тест",
            created_by=self.employee,
            assignee=self.employee,
            priority=Task.Priority.P0,
            status=Task.Status.IN_PROGRESS,
        )

    def headers(self, employee=None):
        employee = employee or self.employee
        return {
            "HTTP_X_AUTH_USER": employee.username,
        }

    def test_employee_can_save_my_filter(self):
        response = self.client.post(
            "/filters/save/",
            {
                "scope": "my",
                "name": "Мои P0",
                "priority": "p0",
                "status": "in_progress",
            },
            **self.headers(),
        )

        self.assertEqual(response.status_code, 302)

        saved_filter = SavedTaskFilter.objects.get(
            employee=self.employee,
            name="Мои P0",
        )

        self.assertEqual(
            saved_filter.scope,
            SavedTaskFilter.Scope.MY,
        )
        self.assertEqual(
            saved_filter.params,
            {
                "priority": "p0",
                "status": "in_progress",
            },
        )

    def test_same_name_updates_existing_filter(self):
        SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.MY,
            name="Работа",
            params={"priority": "p1"},
        )

        self.client.post(
            "/filters/save/",
            {
                "scope": "my",
                "name": "Работа",
                "priority": "p0",
            },
            **self.headers(),
        )

        self.assertEqual(
            SavedTaskFilter.objects.filter(
                employee=self.employee,
                scope=SavedTaskFilter.Scope.MY,
                name="Работа",
            ).count(),
            1,
        )

        self.assertEqual(
            SavedTaskFilter.objects.get(
                employee=self.employee,
                scope=SavedTaskFilter.Scope.MY,
                name="Работа",
            ).params,
            {"priority": "p0"},
        )

    def test_empty_filter_is_rejected(self):
        response = self.client.post(
            "/filters/save/",
            {
                "scope": "my",
                "name": "Пустой",
            },
            **self.headers(),
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            SavedTaskFilter.objects.filter(
                employee=self.employee,
            ).exists()
        )

    def test_unknown_parameters_are_not_saved(self):
        self.client.post(
            "/filters/save/",
            {
                "scope": "my",
                "name": "Безопасный",
                "priority": "p0",
                "evil": "yes",
                "next": "https://example.com",
            },
            **self.headers(),
        )

        saved_filter = SavedTaskFilter.objects.get(
            employee=self.employee,
            name="Безопасный",
        )

        self.assertEqual(
            saved_filter.params,
            {"priority": "p0"},
        )

    def test_filters_are_private_per_employee(self):
        saved_filter = SavedTaskFilter.objects.create(
            employee=self.other,
            scope=SavedTaskFilter.Scope.MY,
            name="Чужой",
            params={"priority": "p0"},
        )

        response = self.client.get(
            f"/filters/{saved_filter.pk}/apply/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 404)

    def test_apply_redirects_to_saved_query(self):
        saved_filter = SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.MY,
            name="Просроченные",
            params={
                "priority": "p0",
                "overdue": "1",
            },
        )

        response = self.client.get(
            f"/filters/{saved_filter.pk}/apply/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("priority=p0", response.url)
        self.assertIn("overdue=1", response.url)

    def test_all_scope_redirects_to_all_tasks(self):
        saved_filter = SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.ALL,
            name="Все P1",
            params={"priority": "p1"},
        )

        response = self.client.get(
            f"/filters/{saved_filter.pk}/apply/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith("/tasks/?")
        )

    def test_employee_can_delete_own_filter(self):
        saved_filter = SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.MY,
            name="Удалить",
            params={"priority": "p0"},
        )

        response = self.client.post(
            f"/filters/{saved_filter.pk}/delete/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            SavedTaskFilter.objects.filter(
                pk=saved_filter.pk,
            ).exists()
        )

    def test_employee_cannot_delete_other_filter(self):
        saved_filter = SavedTaskFilter.objects.create(
            employee=self.other,
            scope=SavedTaskFilter.Scope.MY,
            name="Чужой",
            params={"priority": "p0"},
        )

        response = self.client.post(
            f"/filters/{saved_filter.pk}/delete/",
            **self.headers(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            SavedTaskFilter.objects.filter(
                pk=saved_filter.pk,
            ).exists()
        )


    def test_home_displays_saved_filter(self):
        SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.MY,
            name="Мои P0",
            params={"priority": "p0"},
        )

        response = self.client.get(
            "/",
            **self.headers(),
        )

        self.assertContains(response, "Сохранённые фильтры")
        self.assertContains(response, "Мои P0")

    def test_home_can_offer_save_current_filter(self):
        response = self.client.get(
            "/?priority=p0&status=in_progress",
            **self.headers(),
        )

        self.assertContains(response, "Сохранить текущий")
        self.assertContains(
            response,
            'name="priority"',
            html=False,
        )
        self.assertContains(
            response,
            'value="p0"',
            html=False,
        )

    def test_all_tasks_displays_only_all_scope_filters(self):
        SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.MY,
            name="Только мои",
            params={"priority": "p0"},
        )

        SavedTaskFilter.objects.create(
            employee=self.employee,
            scope=SavedTaskFilter.Scope.ALL,
            name="Общий P0",
            params={"priority": "p0"},
        )

        response = self.client.get(
            "/tasks/",
            **self.headers(),
        )

        self.assertContains(response, "Общий P0")
        self.assertNotContains(response, "Только мои")

    def test_other_employee_filter_is_not_shown(self):
        SavedTaskFilter.objects.create(
            employee=self.other,
            scope=SavedTaskFilter.Scope.MY,
            name="Чужой фильтр",
            params={"priority": "p0"},
        )

        response = self.client.get(
            "/",
            **self.headers(),
        )

        self.assertNotContains(
            response,
            "Чужой фильтр",
        )

    def test_all_tasks_preserves_selected_assignee(self):
        response = self.client.get(
            f"/tasks/?assignee={self.employee.pk}",
            **self.headers(),
        )

        self.assertContains(
            response,
            f'value="{self.employee.pk}"',
            html=False,
        )
        self.assertContains(
            response,
            "selected",
            html=False,
        )

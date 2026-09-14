from django.test import TestCase

from .models import Employee, Task, TaskWatcher


class TaskWatcherTests(TestCase):
    def setUp(self):
        self.member = Employee.objects.create(
            username="watch-member",
            display_name="Наблюдатель",
        )

        self.other = Employee.objects.create(
            username="watch-other",
            display_name="Другой сотрудник",
        )

        self.manager = Employee.objects.create(
            username="watch-manager",
            display_name="Руководитель",
            role=Employee.Role.MANAGER,
        )

        self.task = Task.objects.create(
            code="WATCH-001",
            title="Task watchers",
            created_by=self.manager,
            assignee=self.other,
            status=Task.Status.IN_PROGRESS,
        )

    def test_employee_can_subscribe_self(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/watch/",
            HTTP_X_AUTH_USER=self.member.username,
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.member,
            ).exists()
        )

    def test_second_toggle_unsubscribes_self(self):
        TaskWatcher.objects.create(
            task=self.task,
            employee=self.member,
            added_by=self.member,
        )

        response = self.client.post(
            f"/tasks/{self.task.pk}/watch/",
            HTTP_X_AUTH_USER=self.member.username,
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.member,
            ).exists()
        )

    def test_get_toggle_does_not_mutate(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/watch/",
            HTTP_X_AUTH_USER=self.member.username,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TaskWatcher.objects.count(),
            0,
        )

    def test_unique_watcher_constraint(self):
        TaskWatcher.objects.create(
            task=self.task,
            employee=self.member,
            added_by=self.member,
        )

        self.client.post(
            f"/tasks/{self.task.pk}/watchers/",
            {
                "employee_id": self.member.pk,
                "action": "add",
            },
            HTTP_X_AUTH_USER=self.manager.username,
        )

        self.assertEqual(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.member,
            ).count(),
            1,
        )

    def test_manager_can_add_watcher(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/watchers/",
            {
                "employee_id": self.member.pk,
                "action": "add",
            },
            HTTP_X_AUTH_USER=self.manager.username,
        )

        self.assertEqual(response.status_code, 302)

        watcher = TaskWatcher.objects.get(
            task=self.task,
            employee=self.member,
        )

        self.assertEqual(
            watcher.added_by,
            self.manager,
        )

    def test_manager_can_remove_watcher(self):
        TaskWatcher.objects.create(
            task=self.task,
            employee=self.member,
            added_by=self.manager,
        )

        response = self.client.post(
            f"/tasks/{self.task.pk}/watchers/",
            {
                "employee_id": self.member.pk,
                "action": "remove",
            },
            HTTP_X_AUTH_USER=self.manager.username,
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.member,
            ).exists()
        )

    def test_member_cannot_manage_other_watchers(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/watchers/",
            {
                "employee_id": self.other.pk,
                "action": "add",
            },
            HTTP_X_AUTH_USER=self.member.username,
        )

        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.other,
            ).exists()
        )

    def test_detail_displays_watchers(self):
        TaskWatcher.objects.create(
            task=self.task,
            employee=self.member,
            added_by=self.manager,
        )

        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER=self.other.username,
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Наблюдатели")
        self.assertContains(response, "Наблюдатель")
        self.assertContains(response, "+ Наблюдать")

    def test_watcher_can_exist_on_done_task(self):
        self.task.status = Task.Status.DONE
        self.task.save()

        response = self.client.post(
            f"/tasks/{self.task.pk}/watch/",
            HTTP_X_AUTH_USER=self.member.username,
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            TaskWatcher.objects.filter(
                task=self.task,
                employee=self.member,
            ).exists()
        )

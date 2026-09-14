from django.test import TestCase
from django.utils import timezone

from .models import Employee, Task, TaskComment


class TaskCommentsFeedTests(TestCase):
    def setUp(self):
        self.author = Employee.objects.create(
            username="comment-author",
            display_name="Автор Комментария",
        )

        self.other = Employee.objects.create(
            username="comment-other",
            display_name="Другой Сотрудник",
        )

        self.task = Task.objects.create(
            code="COMMENT-001",
            title="Task with discussion",
            created_by=self.author,
            assignee=self.author,
            priority=Task.Priority.P1,
            status=Task.Status.IN_PROGRESS,
        )

    def test_comment_is_created_with_author(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/comments/",
            {
                "body": "Первый нормальный комментарий",
            },
            HTTP_X_AUTH_USER=self.other.username,
        )

        self.assertEqual(response.status_code, 302)

        comment = TaskComment.objects.get(
            task=self.task,
        )

        self.assertEqual(
            comment.author,
            self.other,
        )

        self.assertEqual(
            comment.body,
            "Первый нормальный комментарий",
        )

        self.assertIsNotNone(
            comment.created_at,
        )

    def test_whitespace_is_stripped(self):
        self.client.post(
            f"/tasks/{self.task.pk}/comments/",
            {
                "body": "   Текст комментария   ",
            },
            HTTP_X_AUTH_USER=self.author.username,
        )

        comment = TaskComment.objects.get()

        self.assertEqual(
            comment.body,
            "Текст комментария",
        )

    def test_empty_comment_is_rejected(self):
        response = self.client.post(
            f"/tasks/{self.task.pk}/comments/",
            {
                "body": "   ",
            },
            HTTP_X_AUTH_USER=self.author.username,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            TaskComment.objects.count(),
            0,
        )

    def test_get_does_not_create_comment(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/comments/",
            HTTP_X_AUTH_USER=self.author.username,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TaskComment.objects.count(),
            0,
        )

    def test_detail_shows_author_body_and_time(self):
        comment = TaskComment.objects.create(
            task=self.task,
            author=self.other,
            body="Комментарий в ленте",
        )

        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER=self.author.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Другой Сотрудник",
        )

        self.assertContains(
            response,
            "Комментарий в ленте",
        )

        self.assertContains(
            response,
            timezone.localtime(
                comment.created_at
            ).strftime("%d.%m.%Y %H:%M"),
        )

    def test_comments_are_oldest_first(self):
        first = TaskComment.objects.create(
            task=self.task,
            author=self.author,
            body="Первый комментарий",
        )

        second = TaskComment.objects.create(
            task=self.task,
            author=self.other,
            body="Второй комментарий",
        )

        comments = list(
            self.task.comments.all()
        )

        self.assertEqual(
            comments,
            [first, second],
        )

    def test_legacy_comment_is_preserved_and_displayed(self):
        self.task.comment = "Исторический комментарий"
        self.task.save()

        response = self.client.get(
            f"/tasks/{self.task.pk}/",
            HTTP_X_AUTH_USER=self.author.username,
        )

        self.assertContains(
            response,
            "Старый комментарий",
        )

        self.assertContains(
            response,
            "Исторический комментарий",
        )

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.comment,
            "Исторический комментарий",
        )

    def test_legacy_comment_not_in_edit_form(self):
        response = self.client.get(
            f"/tasks/{self.task.pk}/edit/",
            HTTP_X_AUTH_USER=self.author.username,
        )

        self.assertEqual(response.status_code, 200)

        self.assertNotContains(
            response,
            'name="comment"',
        )

    def test_can_comment_on_done_task(self):
        self.task.status = Task.Status.DONE
        self.task.save()

        response = self.client.post(
            f"/tasks/{self.task.pk}/comments/",
            {
                "body": "Комментарий после завершения",
            },
            HTTP_X_AUTH_USER=self.other.username,
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            TaskComment.objects.filter(
                task=self.task,
                author=self.other,
                body="Комментарий после завершения",
            ).exists()
        )

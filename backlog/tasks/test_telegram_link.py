from datetime import timedelta

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Employee, TelegramLinkRequest
from .telegram import create_link_request


class TelegramLinkTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            username="worker",
            display_name="Worker",
        )

    def test_link_page_requires_matching_employee(self):
        _, token = create_link_request(
            employee=self.employee,
            telegram_user_id=1001,
            telegram_chat_id=2001,
            telegram_username="worker_tg",
        )

        other = Employee.objects.create(
            username="other",
            display_name="Other",
        )

        response = self.client.get(
            f"/telegram/link/{token}/",
            HTTP_X_AUTH_USER=other.username,
        )

        self.assertEqual(
            response.status_code,
            403,
        )

    @patch("tasks.telegram.send_message")
    def test_employee_can_link_telegram(self, send_message):
        _, token = create_link_request(
            employee=self.employee,
            telegram_user_id=1001,
            telegram_chat_id=2001,
            telegram_username="worker_tg",
        )

        response = self.client.post(
            f"/telegram/link/{token}/",
            HTTP_X_AUTH_USER=self.employee.username,
        )

        self.assertEqual(
            response.status_code,
            200,
        )

        self.employee.refresh_from_db()

        self.assertEqual(
            self.employee.telegram_user_id,
            1001,
        )

        self.assertEqual(
            self.employee.telegram_chat_id,
            2001,
        )

    def test_expired_link_is_rejected(self):
        link, token = create_link_request(
            employee=self.employee,
            telegram_user_id=1001,
            telegram_chat_id=2001,
        )

        link.expires_at = (
            timezone.now()
            - timedelta(minutes=1)
        )
        link.save(update_fields=["expires_at"])

        response = self.client.get(
            f"/telegram/link/{token}/",
            HTTP_X_AUTH_USER=self.employee.username,
        )

        self.assertEqual(
            response.status_code,
            410,
        )


class TelegramBotMenuTests(TestCase):
    @patch(
        "tasks.management.commands.run_telegram_bot.send_message"
    )
    def test_authorize_message_shows_employee_keyboard(
        self,
        send_message,
    ):
        from tasks.management.commands.run_telegram_bot import Command

        Employee.objects.create(
            username="vasiliy",
            display_name="Василий",
        )

        Employee.objects.create(
            username="admin",
            display_name="admin",
        )

        command = Command()

        command.handle_authorize(
            {
                "chat": {"id": 123},
                "from": {"id": 456},
                "text": "Авторизоваться",
            }
        )

        markup = send_message.call_args.kwargs[
            "reply_markup"
        ]

        text = str(markup)

        self.assertIn("Василий", text)
        self.assertNotIn("admin", text)

    @patch(
        "tasks.management.commands.run_telegram_bot."
        "create_link_request"
    )
    @patch(
        "tasks.management.commands.run_telegram_bot.send_message"
    )
    def test_employee_message_creates_confirmation_link(
        self,
        send_message,
        create_link_request,
    ):
        from tasks.management.commands.run_telegram_bot import Command

        Employee.objects.create(
            username="vasiliy",
            display_name="Василий",
        )

        create_link_request.return_value = (
            object(),
            "test-token",
        )

        command = Command()

        command.handle_employee_selection(
            {
                "chat": {"id": 123},
                "from": {
                    "id": 456,
                    "username": "testuser",
                },
            },
            "https://backlog.example.com",
            "👤 Василий",
        )

        create_link_request.assert_called_once()

        markup = send_message.call_args.kwargs[
            "reply_markup"
        ]

        self.assertIn(
            "https://backlog.example.com/telegram/link/test-token/",
            str(markup),
        )

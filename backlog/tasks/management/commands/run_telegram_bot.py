import json
import os
import time

from django.core.management.base import BaseCommand

from tasks.models import Employee
from tasks.telegram import (
    answer_callback,
    confirm_link_keyboard,
    create_link_request,
    employee_keyboard,
    send_message,
    telegram_api,
)


class Command(BaseCommand):
    help = "Run Telegram backlog bot using long polling."

    def handle(self, *args, **options):
        base_url = os.environ["BACKLOG_BASE_URL"].rstrip("/")
        offset = None

        self.stdout.write(
            self.style.SUCCESS(
                "Telegram bot polling started."
            )
        )

        while True:
            try:
                payload = {
                    "timeout": 25,
                    "allowed_updates": json.dumps(
                        ["message", "callback_query"]
                    ),
                }

                if offset is not None:
                    payload["offset"] = offset

                updates = telegram_api(
                    "getUpdates",
                    payload,
                    timeout=35,
                )

                for update in updates:
                    offset = update["update_id"] + 1
                    self.process_update(
                        update,
                        base_url,
                    )

            except KeyboardInterrupt:
                return

            except Exception as exc:
                self.stderr.write(
                    f"Telegram bot error: {exc}"
                )
                time.sleep(5)

    def process_update(self, update, base_url):
        message = update.get("message")

        if message:
            text = (message.get("text") or "").strip()

            telegram_date = message.get("date")
            if telegram_date:
                delay = time.time() - telegram_date
                self.stdout.write(
                    f"TG update received: command={text[:40]!r} "
                    f"telegram_to_bot={delay:.3f}s"
                )

            if text == "/ping":
                started = time.monotonic()
                send_message(
                    message["chat"]["id"],
                    "pong",
                )
                elapsed = time.monotonic() - started
                self.stdout.write(
                    f"TG sendMessage completed: {elapsed:.3f}s"
                )
                return

            if text.startswith("/start"):
                self.handle_start(message)
                return

            if text == "Авторизоваться":
                self.handle_authorize(message)
                return

            if text.startswith("👤 "):
                self.handle_employee_selection(
                    message,
                    base_url,
                    text,
                )
                return

            return

        callback = update.get("callback_query")

        if not callback:
            return

        data = callback.get("data") or ""

        if data == "show_employees":
            chat = (
                callback.get("message", {})
                .get("chat", {})
            )

            chat_id = chat.get(
                "id",
                callback["from"]["id"],
            )

            answer_callback(
                callback["id"],
            )

            send_message(
                chat_id,
                "Выберите себя:",
                reply_markup=employee_keyboard(),
            )

            return

        if not data.startswith("link_employee:"):
            return

        try:
            employee_id = int(
                data.split(":", 1)[1]
            )
        except ValueError:
            return

        employee = Employee.objects.filter(
            pk=employee_id,
            is_active=True,
        ).exclude(
            username__in=["backlog_import", "admin"],
        ).first()

        if not employee:
            answer_callback(
                callback["id"],
                "Сотрудник не найден.",
            )
            return

        telegram_user = callback["from"]

        chat = (
            callback.get("message", {})
            .get("chat", {})
        )

        telegram_user_id = telegram_user["id"]
        chat_id = chat.get(
            "id",
            telegram_user_id,
        )

        linked = Employee.objects.filter(
            telegram_user_id=telegram_user_id,
        ).first()

        if linked:
            answer_callback(
                callback["id"],
                (
                    "Telegram уже привязан: "
                    f"{linked.display_name or linked.username}"
                ),
            )
            return

        if (
            employee.telegram_user_id
            and employee.telegram_user_id
            != telegram_user_id
        ):
            answer_callback(
                callback["id"],
                "Этот сотрудник уже привязан.",
            )
            return

        link, raw_token = create_link_request(
            employee=employee,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=chat_id,
            telegram_username=(
                telegram_user.get("username") or ""
            ),
        )

        url = (
            f"{base_url}/telegram/link/"
            f"{raw_token}/"
        )

        answer_callback(
            callback["id"],
            "Откройте ссылку для подтверждения.",
        )

        send_message(
            chat_id,
            (
                "Вы выбрали сотрудника:\n"
                f"{employee.display_name or employee.username}\n\n"
                "Подтвердите привязку через Backlog."
            ),
            reply_markup=confirm_link_keyboard(
                url
            ),
        )

    def handle_authorize(self, message):
        chat_id = message["chat"]["id"]

        employees = (
            Employee.objects
            .filter(is_active=True)
            .exclude(
                username__in=[
                    "backlog_import",
                    "admin",
                ]
            )
            .order_by(
                "display_name",
                "username",
            )
        )

        keyboard = []

        for employee in employees:
            name = (
                employee.display_name
                or employee.username
            )

            keyboard.append([
                {
                    "text": f"👤 {name}",
                }
            ])

        send_message(
            chat_id,
            "Выберите себя:",
            reply_markup={
                "keyboard": keyboard,
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    def handle_employee_selection(
        self,
        message,
        base_url,
        text,
    ):
        telegram_user = message["from"]
        chat_id = message["chat"]["id"]

        selected_name = text[2:].strip()

        employees = (
            Employee.objects
            .filter(is_active=True)
            .exclude(
                username__in=[
                    "backlog_import",
                    "admin",
                ]
            )
        )

        employee = None

        for candidate in employees:
            name = (
                candidate.display_name
                or candidate.username
            )

            if name == selected_name:
                employee = candidate
                break

        if not employee:
            send_message(
                chat_id,
                "Сотрудник не найден. Нажмите /start.",
            )
            return

        linked = Employee.objects.filter(
            telegram_user_id=telegram_user["id"],
        ).first()

        if linked:
            send_message(
                chat_id,
                (
                    "Telegram уже привязан к сотруднику: "
                    f"{linked.display_name or linked.username}"
                ),
            )
            return

        if (
            employee.telegram_user_id
            and employee.telegram_user_id
            != telegram_user["id"]
        ):
            send_message(
                chat_id,
                "Этот сотрудник уже привязан к другому Telegram.",
            )
            return

        _, raw_token = create_link_request(
            employee=employee,
            telegram_user_id=telegram_user["id"],
            telegram_chat_id=chat_id,
            telegram_username=(
                telegram_user.get("username") or ""
            ),
        )

        url = (
            f"{base_url}/telegram/link/"
            f"{raw_token}/"
        )

        send_message(
            chat_id,
            (
                f"Вы выбрали: "
                f"{employee.display_name or employee.username}\n\n"
                "Теперь подтвердите привязку через Backlog."
            ),
            reply_markup=confirm_link_keyboard(
                url
            ),
        )

    def handle_start(self, message):
        telegram_user = message["from"]
        chat_id = message["chat"]["id"]

        linked = Employee.objects.filter(
            telegram_user_id=telegram_user["id"],
        ).first()

        if linked:
            send_message(
                chat_id,
                (
                    "✅ Telegram уже привязан.\n\n"
                    "Сотрудник: "
                    f"{linked.display_name or linked.username}"
                ),
            )
            return

        send_message(
            chat_id,
            (
                "Бэклог отдела заботы.\n\n"
                "Нажмите «Авторизоваться» "
                "и выберите себя из списка."
            ),
            reply_markup={
                "keyboard": [
                    [
                        {
                            "text": "Авторизоваться",
                        }
                    ]
                ],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

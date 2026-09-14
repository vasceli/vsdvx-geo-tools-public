import time

from django.core.management.base import BaseCommand

from tasks.notifications import (
    deliver_pending_outbox,
    enqueue_overdue_tasks,
)


class Command(BaseCommand):
    help = (
        "Send durable Telegram notifications "
        "and detect overdue tasks."
    )

    def handle(self, *args, **options):
        next_overdue_check = 0.0

        self.stdout.write(
            self.style.SUCCESS(
                "Telegram notifier started."
            )
        )

        while True:
            try:
                now = time.monotonic()

                if now >= next_overdue_check:
                    queued = enqueue_overdue_tasks()

                    if queued:
                        self.stdout.write(
                            f"Queued overdue notifications: "
                            f"{queued}"
                        )

                    next_overdue_check = now + 60

                sent, failed = deliver_pending_outbox(
                    limit=50
                )

                if sent or failed:
                    self.stdout.write(
                        f"Telegram outbox: "
                        f"sent={sent} failed={failed}"
                    )

                time.sleep(
                    0.25
                    if sent
                    else 2
                )

            except KeyboardInterrupt:
                return

            except Exception as exc:
                self.stderr.write(
                    f"Telegram notifier error: {exc}"
                )
                time.sleep(5)

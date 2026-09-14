import csv
import re
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from tasks.models import Employee, Task, TaskHistory


MOSCOW = ZoneInfo("Europe/Moscow")

PRIORITY_MAP = {
    "Ожидает оценки": Task.Priority.WAITING,
    "P0 — критично": Task.Priority.P0,
    "P1 — высокий": Task.Priority.P1,
    "P2 — средний": Task.Priority.P2,
    "P3 — низкий": Task.Priority.P3,
    "Стоп": Task.Priority.STOP,
}

STATUS_MAP = {
    "Идея": Task.Status.IDEA,
    "Новая": Task.Status.NEW,
    "Запланирована": Task.Status.PLANNED,
    "В работе": Task.Status.IN_PROGRESS,
    "Заблокирована": Task.Status.BLOCKED,
    "На проверке": Task.Status.REVIEW,
    "Готово": Task.Status.DONE,
    "Отменена": Task.Status.CANCELLED,
}

TASK_CODE_RE = re.compile(r"^TASK-\d+$")


def clean(value):
    return (value or "").strip()


def parse_mapping(values):
    result = {}

    for item in values:
        if "=" not in item:
            raise CommandError(
                f"Invalid --map-assignee value: {item!r}. "
                "Expected SOURCE=username"
            )

        source, username = item.split("=", 1)
        source = clean(source)
        username = clean(username)

        if not source or not username:
            raise CommandError(
                f"Invalid --map-assignee value: {item!r}"
            )

        result[source] = username

    return result


def make_aware(value):
    if timezone.is_aware(value):
        return value
    return value.replace(tzinfo=MOSCOW)


def parse_datetime(value, *, reference_year=None, deadline=False):
    value = clean(value)

    if not value:
        return None

    # Example from the current sheet: "06.08 до 12:00"
    match = re.fullmatch(
        r"(\d{1,2})\.(\d{1,2})\s+до\s+(\d{1,2}):(\d{2})",
        value,
        flags=re.IGNORECASE,
    )

    if match:
        if reference_year is None:
            raise CommandError(
                f"Cannot infer year for datetime {value!r}"
            )

        day, month, hour, minute = map(int, match.groups())

        return make_aware(
            datetime(
                reference_year,
                month,
                day,
                hour,
                minute,
            )
        )

    datetime_formats = (
        "%H:%M %d.%m.%Y",
        "%H:%M %d.%m.%y",
        "%d.%m.%Y %H:%M",
        "%d.%m.%y %H:%M",
    )

    for fmt in datetime_formats:
        try:
            return make_aware(datetime.strptime(value, fmt))
        except ValueError:
            pass

    date_formats = (
        "%d.%m.%Y",
        "%d.%m.%y",
    )

    for fmt in date_formats:
        try:
            date_value = datetime.strptime(value, fmt).date()

            if deadline:
                return make_aware(
                    datetime.combine(
                        date_value,
                        time(23, 59, 59),
                    )
                )

            return make_aware(
                datetime.combine(
                    date_value,
                    time.min,
                )
            )
        except ValueError:
            pass

    raise CommandError(
        f"Unsupported date/time format: {value!r}"
    )


def parse_decimal(value):
    value = clean(value)

    if not value:
        return None

    try:
        return Decimal(value.replace(",", "."))
    except InvalidOperation:
        raise CommandError(
            f"Invalid estimate value: {value!r}"
        )


class Command(BaseCommand):
    help = "One-time import of the legacy Google Sheets backlog CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

        parser.add_argument(
            "--map-assignee",
            action="append",
            default=[],
            metavar="SOURCE=username",
        )

        parser.add_argument(
            "--expected-count",
            type=int,
            default=None,
        )

        parser.add_argument(
            "--dry-run",
            action="store_true",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])

        if not csv_path.is_file():
            raise CommandError(
                f"CSV file not found: {csv_path}"
            )

        if Task.objects.exists():
            raise CommandError(
                "Task table is not empty. "
                "Import is intentionally allowed only into an empty backlog."
            )

        assignee_map = parse_mapping(
            options["map_assignee"]
        )

        with csv_path.open(
            "r",
            encoding="utf-8-sig",
            newline="",
        ) as file:
            rows = list(csv.reader(file))

        header_index = None

        for index, row in enumerate(rows):
            normalized = [clean(x) for x in row]

            if (
                normalized
                and normalized[0] == "ID"
                and "Задача" in normalized
            ):
                header_index = index
                break

        if header_index is None:
            raise CommandError(
                "Backlog header row was not found."
            )

        headers = [
            clean(value)
            for value in rows[header_index]
        ]

        if len(headers) > 6 and not headers[6]:
            headers[6] = "Исполнитель"

        source_rows = []

        for row_number, row in enumerate(
            rows[header_index + 1:],
            start=header_index + 2,
        ):
            padded = list(row) + [""] * (
                len(headers) - len(row)
            )

            raw = {
                headers[i]: padded[i]
                if i < len(padded)
                else ""
                for i in range(len(headers))
            }

            code = clean(raw.get("ID"))
            title = clean(raw.get("Задача"))

            # TASK-050/TASK-051 and other prefilled empty rows.
            if not code or not title:
                continue

            if not TASK_CODE_RE.fullmatch(code):
                raise CommandError(
                    f"Row {row_number}: invalid task ID {code!r}"
                )

            source_rows.append(
                (row_number, raw)
            )

        expected = options["expected_count"]

        if (
            expected is not None
            and len(source_rows) != expected
        ):
            raise CommandError(
                f"Expected {expected} tasks, "
                f"found {len(source_rows)}."
            )

        import_actor, _ = Employee.objects.get_or_create(
            username="backlog_import",
            defaults={
                "display_name": "Импорт Google Sheets",
                "is_active": False,
            },
        )

        imported = 0

        for sequence, (row_number, raw) in enumerate(
            source_rows,
            start=1,
        ):
            legacy_code = clean(raw["ID"])
            code = f"TASK-{sequence:03d}"

            priority_text = clean(
                raw.get("Приоритет Дмитрия")
            )

            status_text = clean(
                raw.get("Статус")
            )

            if not priority_text:
                priority = Task.Priority.WAITING
            else:
                try:
                    priority = PRIORITY_MAP[priority_text]
                except KeyError:
                    raise CommandError(
                        f"{code}: unknown priority "
                        f"{priority_text!r}"
                    )

            if not status_text:
                status = Task.Status.NEW
            else:
                try:
                    status = STATUS_MAP[status_text]
                except KeyError:
                    raise CommandError(
                        f"{code}: unknown status "
                        f"{status_text!r}"
                    )

            source_assignee = clean(
                raw.get("Исполнитель")
            )

            assignee = None

            if source_assignee:
                username = assignee_map.get(
                    source_assignee
                )

                if not username:
                    raise CommandError(
                        f"{code}: assignee "
                        f"{source_assignee!r} has no mapping"
                    )

                assignee, _ = Employee.objects.get_or_create(
                    username=username,
                    defaults={
                        "display_name": source_assignee,
                    },
                )

            created_dt = parse_datetime(
                raw.get("Дата создания")
            )

            reference_year = (
                created_dt.year
                if created_dt
                else None
            )

            due_dt = parse_datetime(
                raw.get("Срок"),
                reference_year=reference_year,
                deadline=True,
            )

            updated_dt = parse_datetime(
                raw.get("Обновлено"),
                reference_year=reference_year,
            )

            completed_dt = parse_datetime(
                raw.get("Дата завершения"),
                reference_year=reference_year,
            )

            task = Task.objects.create(
                code=code,
                title=clean(raw.get("Задача")),
                acceptance_criteria=clean(
                    raw.get(
                        "Результат / критерий готовности"
                    )
                ),
                reporter=clean(
                    raw.get("Кто поставил")
                ),
                direction=clean(
                    raw.get("Направление")
                ),
                created_by=import_actor,
                assignee=assignee,
                priority=priority,
                status=status,
                due_at=due_dt,
                estimate_hours=parse_decimal(
                    raw.get("Оценка, ч")
                ),
                blockers=clean(
                    raw.get(
                        "Зависимости / блокеры"
                    )
                ),
                next_step=clean(
                    raw.get("Следующий шаг")
                ),
                materials_url=clean(
                    raw.get("Ссылка / материалы")
                ),
                comment=clean(
                    raw.get("Комментарий")
                ),
                completed_at=completed_dt,
                source_data={
                    "__legacy_id": legacy_code,
                    "__source_row": row_number,
                    **{
                        key: (
                            "" if value is None else str(value)
                        )
                        for key, value in raw.items()
                    },
                },
            )

            timestamp_updates = {}

            if created_dt:
                timestamp_updates["created_at"] = created_dt

            if updated_dt:
                timestamp_updates["updated_at"] = updated_dt
            elif created_dt:
                timestamp_updates["updated_at"] = created_dt

            if timestamp_updates:
                Task.objects.filter(
                    pk=task.pk
                ).update(**timestamp_updates)

            TaskHistory.objects.create(
                task=task,
                actor=import_actor,
                field_name="import",
                old_value="",
                new_value=(
                    f"Google Sheets row {row_number}"
                ),
            )

            imported += 1

        if options["dry_run"]:
            transaction.set_rollback(True)

            self.stdout.write(
                self.style.WARNING(
                    f"DRY RUN OK: {imported} tasks validated; "
                    "database rolled back."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {imported} tasks."
            )
        )

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tasks.models import Employee


class Command(BaseCommand):
    help = "Assign the only backlog manager."

    def add_arguments(self, parser):
        parser.add_argument("username")

    @transaction.atomic
    def handle(self, *args, **options):
        username = options["username"]

        try:
            employee = Employee.objects.get(username=username)
        except Employee.DoesNotExist:
            raise CommandError(
                f"Employee '{username}' does not exist in backlog yet."
            )

        Employee.objects.filter(
            role=Employee.Role.MANAGER
        ).exclude(
            pk=employee.pk
        ).update(
            role=Employee.Role.MEMBER
        )

        employee.role = Employee.Role.MANAGER
        employee.save(update_fields=["role"])

        self.stdout.write(
            self.style.SUCCESS(
                f"{username} is now the only backlog manager."
            )
        )

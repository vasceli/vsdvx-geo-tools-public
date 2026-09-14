from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0011_normalize_task_directions"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="employee",
            name="backlog_single_manager",
        ),
    ]

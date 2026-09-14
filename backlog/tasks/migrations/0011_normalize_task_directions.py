from django.db import migrations


DIRECTION_NORMALIZATION = {
    "Отчетность": "Отчётность",
    "тест": "Другое",
    "Оля": "Другое",
}


def normalize_task_directions(apps, schema_editor):
    Task = apps.get_model("tasks", "Task")

    for old_value, new_value in (
        DIRECTION_NORMALIZATION.items()
    ):
        Task.objects.filter(
            direction=old_value,
        ).update(
            direction=new_value,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("tasks", "0010_savedtaskfilter"),
    ]

    operations = [
        migrations.RunPython(
            normalize_task_directions,
            migrations.RunPython.noop,
        ),
    ]

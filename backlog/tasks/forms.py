from django import forms

from .directions import DIRECTION_CHOICES
from .models import Employee, Task


TERMINAL_STATUSES = {
    Task.Status.DONE,
    Task.Status.CANCELLED,
}


def restrict_terminal_statuses(form):
    current_status = (
        form.instance.status
        if form.instance and form.instance.pk
        else None
    )

    form.fields["status"].choices = [
        choice
        for choice in Task.Status.choices
        if (
            choice[0] not in TERMINAL_STATUSES
            or choice[0] == current_status
        )
    ]


class TaskCreateForm(forms.ModelForm):
    direction = forms.ChoiceField(
        label="Направление",
        choices=DIRECTION_CHOICES,
        required=True,
        error_messages={
            "required": "Выберите направление.",
            "invalid_choice": "Выберите направление из списка.",
        },
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "acceptance_criteria",
            "reporter",
            "direction",
            "next_step",
            "materials_url",
        ]
        labels = {
            "title": "Название",
            "acceptance_criteria": "Критерии готовности",
            "reporter": "Постановщик",
            "direction": "Направление",
            "next_step": "Следующий шаг",
            "materials_url": "Ссылка на материалы",
        }
        widgets = {
            "title": forms.Textarea(attrs={"rows": 2}),
            "acceptance_criteria": forms.Textarea(attrs={"rows": 4}),
            "next_step": forms.Textarea(attrs={"rows": 3}),
            "materials_url": forms.TextInput(
                attrs={
                    "placeholder": "https://...",
                }
            ),
        }


class MemberTaskUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "status",
            "next_step",
            "blockers",
            "materials_url",
        ]
        labels = {
            "status": "Статус",
            "next_step": "Следующий шаг",
            "blockers": "Блокеры",
            "materials_url": "Ссылка на материалы",
        }
        widgets = {
            "next_step": forms.Textarea(attrs={"rows": 3}),
            "blockers": forms.Textarea(attrs={"rows": 3}),
            "materials_url": forms.TextInput(
                attrs={
                    "placeholder": "https://...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        restrict_terminal_statuses(self)


class ManagerTaskUpdateForm(forms.ModelForm):
    direction = forms.ChoiceField(
        label="Направление",
        choices=DIRECTION_CHOICES,
        required=True,
        error_messages={
            "required": "Выберите направление.",
            "invalid_choice": "Выберите направление из списка.",
        },
    )

    due_at = forms.DateTimeField(
        label="Срок",
        required=False,
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=["%Y-%m-%dT%H:%M"],
    )

    class Meta:
        model = Task
        fields = [
            "title",
            "acceptance_criteria",
            "reporter",
            "direction",
            "assignee",
            "priority",
            "status",
            "due_at",
            "estimate_hours",
            "blockers",
            "next_step",
            "materials_url",
        ]
        labels = {
            "title": "Название",
            "acceptance_criteria": "Критерии готовности",
            "reporter": "Постановщик",
            "direction": "Направление",
            "assignee": "Исполнитель",
            "priority": "Приоритет",
            "status": "Статус",
            "due_at": "Срок",
            "estimate_hours": "Оценка, часов",
            "blockers": "Блокеры",
            "next_step": "Следующий шаг",
            "materials_url": "Ссылка на материалы",
        }
        widgets = {
            "title": forms.Textarea(attrs={"rows": 2}),
            "acceptance_criteria": forms.Textarea(attrs={"rows": 4}),
            "blockers": forms.Textarea(attrs={"rows": 3}),
            "next_step": forms.Textarea(attrs={"rows": 3}),
            "materials_url": forms.TextInput(
                attrs={
                    "placeholder": "https://...",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["assignee"].queryset = Employee.objects.filter(
            is_active=True
        )

        restrict_terminal_statuses(self)

        if self.instance and self.instance.due_at:
            self.initial["due_at"] = (
                self.instance.due_at.strftime("%Y-%m-%dT%H:%M")
            )



class TaskCommentForm(forms.Form):
    body = forms.CharField(
        label="Комментарий",
        max_length=5000,
        widget=forms.Textarea(
            attrs={
                "rows": 4,
                "placeholder": "Написать комментарий...",
            }
        ),
    )

    def clean_body(self):
        body = self.cleaned_data["body"].strip()

        if not body:
            raise forms.ValidationError(
                "Комментарий не может быть пустым."
            )

        return body


class TaskReopenForm(forms.Form):
    status = forms.ChoiceField(
        label="Вернуть в статус",
        choices=[
            (Task.Status.IN_PROGRESS, "В работе"),
            (Task.Status.NEW, "Новая"),
        ],
    )


class TaskCompletionForm(forms.Form):
    status = forms.ChoiceField(
        label="Статус завершения",
        choices=[
            (Task.Status.DONE, "Готово"),
            (Task.Status.CANCELLED, "Отменена"),
        ],
    )

    result = forms.CharField(
        label="Результат",
        required=True,
        widget=forms.Textarea(
            attrs={
                "rows": 5,
                "placeholder": (
                    "Что сделано и какой результат получен"
                ),
            }
        ),
    )

    result_url = forms.URLField(
        label="Ссылка на результат",
        required=False,
        max_length=1000,
        widget=forms.URLInput(
            attrs={
                "placeholder": (
                    "https://disk.yandex.ru/... "
                    "или https://drive.google.com/..."
                ),
            }
        ),
    )

    def clean_result_url(self):
        value = self.cleaned_data.get("result_url", "")

        if value and not value.startswith("https://"):
            raise forms.ValidationError(
                "Ссылка должна начинаться с https://"
            )

        return value

from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    ManagerTaskUpdateForm,
    MemberTaskUpdateForm,
    TaskCommentForm,
    TaskCreateForm,
    TaskReopenForm,
)
from .models import (
    Employee,
    SavedTaskFilter,
    Task,
    TaskComment,
    TaskWatcher,
    format_duration,
)
from .notifications import (
    enqueue_assignment,
    enqueue_comment,
    enqueue_completion,
    enqueue_status_change,
)
from .services import create_task, record_changes


PRIORITY_ORDER = Case(
    When(priority=Task.Priority.P0, then=Value(0)),
    When(priority=Task.Priority.P1, then=Value(1)),
    When(priority=Task.Priority.P2, then=Value(2)),
    When(priority=Task.Priority.P3, then=Value(3)),
    When(priority=Task.Priority.WAITING, then=Value(4)),
    When(priority=Task.Priority.STOP, then=Value(5)),
    default=Value(99),
    output_field=IntegerField(),
)


def task_action_redirect(request, task):
    next_url = request.POST.get("next", "").strip()

    if (
        next_url
        and url_has_allowed_host_and_scheme(
            next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        )
    ):
        return redirect(next_url)

    return redirect(
        "task_detail",
        pk=task.pk,
    )


def ordered(queryset):
    return queryset.annotate(
        priority_order=PRIORITY_ORDER
    ).order_by(
        "priority_order",
        "due_at",
        "-created_at",
    )



def watcher_context(task, employee):
    watcher_links = list(
        task.watcher_links
        .select_related(
            "employee",
            "added_by",
        )
        .all()
    )

    watcher_ids = {
        item.employee_id
        for item in watcher_links
    }

    if employee.can_manage_tasks:
        available_watchers = (
            Employee.objects
            .filter(is_active=True)
            .exclude(pk__in=watcher_ids)
            .order_by(
                "display_name",
                "username",
            )
        )
    else:
        available_watchers = Employee.objects.none()

    return {
        "watcher_links": watcher_links,
        "is_watching": employee.pk in watcher_ids,
        "available_watchers": available_watchers,
    }



SAVED_FILTER_ALLOWED_PARAMS = {
    SavedTaskFilter.Scope.MY: {
        "q",
        "status",
        "priority",
        "direction",
        "overdue",
        "hide_review",
        "sort",
    },
    SavedTaskFilter.Scope.ALL: {
        "q",
        "status",
        "priority",
        "assignee",
    },
}


def saved_filter_params(request, scope):
    allowed = SAVED_FILTER_ALLOWED_PARAMS[scope]
    params = {}

    for key in allowed:
        values = [
            value.strip()
            for value in request.GET.getlist(key)
            if value.strip()
        ]

        if not values:
            continue

        params[key] = (
            values[0]
            if len(values) == 1
            else values
        )

    return params


def saved_filters_for(employee, scope):
    return employee.saved_task_filters.filter(
        scope=scope,
    )


def saved_filter_query(saved_filter):
    from django.http import QueryDict

    query = QueryDict("", mutable=True)

    for key, value in saved_filter.params.items():
        if isinstance(value, list):
            query.setlist(
                key,
                [str(item) for item in value],
            )
        else:
            query[key] = str(value)

    return query.urlencode()


@transaction.atomic
def saved_filter_create(request):
    if request.method != "POST":
        return HttpResponseBadRequest(
            "Используйте POST."
        )

    scope = request.POST.get("scope", "").strip()
    name = request.POST.get("name", "").strip()

    if scope not in SAVED_FILTER_ALLOWED_PARAMS:
        return HttpResponseBadRequest(
            "Неизвестный раздел фильтра."
        )

    if not name:
        return HttpResponseBadRequest(
            "Укажите название фильтра."
        )

    if len(name) > 100:
        return HttpResponseBadRequest(
            "Название фильтра слишком длинное."
        )

    allowed = SAVED_FILTER_ALLOWED_PARAMS[scope]
    params = {}

    for key in allowed:
        values = [
            value.strip()
            for value in request.POST.getlist(key)
            if value.strip()
        ]

        if not values:
            continue

        params[key] = (
            values[0]
            if len(values) == 1
            else values
        )

    if not params:
        return HttpResponseBadRequest(
            "Нельзя сохранить пустой фильтр."
        )

    SavedTaskFilter.objects.update_or_create(
        employee=request.employee,
        scope=scope,
        name=name,
        defaults={
            "params": params,
        },
    )

    if scope == SavedTaskFilter.Scope.ALL:
        return redirect("all_tasks")

    return redirect("home")


@transaction.atomic
def saved_filter_delete(request, pk):
    if request.method != "POST":
        return HttpResponseBadRequest(
            "Используйте POST."
        )

    saved_filter = get_object_or_404(
        SavedTaskFilter,
        pk=pk,
        employee=request.employee,
    )

    scope = saved_filter.scope
    saved_filter.delete()

    if scope == SavedTaskFilter.Scope.ALL:
        return redirect("all_tasks")

    return redirect("home")


def saved_filter_apply(request, pk):
    saved_filter = get_object_or_404(
        SavedTaskFilter,
        pk=pk,
        employee=request.employee,
    )

    query = saved_filter_query(saved_filter)

    if saved_filter.scope == SavedTaskFilter.Scope.ALL:
        base = "/tasks/"
    else:
        base = "/"

    if query:
        return redirect(f"{base}?{query}")

    return redirect(base)

def telegram_link(request, token):
    from .telegram import find_link_request, send_message

    link = find_link_request(token)

    if (
        not link
        or link.is_consumed
        or link.expires_at <= timezone.now()
    ):
        return HttpResponse(
            "Ссылка недействительна или истекла.",
            status=410,
        )

    if request.employee.pk != link.employee_id:
        return HttpResponseForbidden(
            "Эта ссылка предназначена для другого сотрудника."
        )

    if request.method == "POST":
        existing_user = Employee.objects.filter(
            telegram_user_id=link.telegram_user_id,
        ).exclude(pk=link.employee_id).exists()

        existing_chat = Employee.objects.filter(
            telegram_chat_id=link.telegram_chat_id,
        ).exclude(pk=link.employee_id).exists()

        if existing_user or existing_chat:
            return HttpResponseForbidden(
                "Этот Telegram уже привязан к другой учётной записи."
            )

        employee = link.employee

        employee.telegram_user_id = link.telegram_user_id
        employee.telegram_chat_id = link.telegram_chat_id
        employee.telegram_username = link.telegram_username
        employee.telegram_linked_at = timezone.now()

        employee.save(
            update_fields=[
                "telegram_user_id",
                "telegram_chat_id",
                "telegram_username",
                "telegram_linked_at",
            ]
        )

        link.consumed_at = timezone.now()
        link.save(update_fields=["consumed_at"])

        try:
            send_message(
                employee.telegram_chat_id,
                (
                    "✅ Telegram успешно привязан к Backlog.\n\n"
                    f"Сотрудник: {employee.display_name or employee.username}"
                ),
            )
        except Exception:
            pass

        return render(
            request,
            "tasks/telegram_link.html",
            {
                "employee": employee,
                "linked": True,
            },
        )

    return render(
        request,
        "tasks/telegram_link.html",
        {
            "employee": link.employee,
            "linked": False,
        },
    )


def telegram_link(request, token):
    from .telegram import find_link_request, send_message

    link = find_link_request(token)

    if (
        not link
        or link.is_consumed
        or link.expires_at <= timezone.now()
    ):
        return HttpResponse(
            "Ссылка недействительна или истекла.",
            status=410,
        )

    if request.employee.pk != link.employee_id:
        return HttpResponseForbidden(
            "Эта ссылка предназначена для другого сотрудника."
        )

    if request.method == "POST":
        existing_user = Employee.objects.filter(
            telegram_user_id=link.telegram_user_id,
        ).exclude(pk=link.employee_id).exists()

        existing_chat = Employee.objects.filter(
            telegram_chat_id=link.telegram_chat_id,
        ).exclude(pk=link.employee_id).exists()

        if existing_user or existing_chat:
            return HttpResponseForbidden(
                "Этот Telegram уже привязан к другой учётной записи."
            )

        employee = link.employee

        employee.telegram_user_id = link.telegram_user_id
        employee.telegram_chat_id = link.telegram_chat_id
        employee.telegram_username = link.telegram_username
        employee.telegram_linked_at = timezone.now()

        employee.save(
            update_fields=[
                "telegram_user_id",
                "telegram_chat_id",
                "telegram_username",
                "telegram_linked_at",
            ]
        )

        link.consumed_at = timezone.now()
        link.save(update_fields=["consumed_at"])

        try:
            send_message(
                employee.telegram_chat_id,
                (
                    "✅ Telegram успешно привязан к Backlog.\n\n"
                    f"Сотрудник: {employee.display_name or employee.username}"
                ),
            )
        except Exception:
            pass

        return render(
            request,
            "tasks/telegram_link.html",
            {
                "employee": employee,
                "linked": True,
            },
        )

    return render(
        request,
        "tasks/telegram_link.html",
        {
            "employee": link.employee,
            "linked": False,
        },
    )


def healthz(request):
    return HttpResponse("ok", content_type="text/plain")



DASHBOARD_TERMINAL_STATUSES = [
    Task.Status.DONE,
    Task.Status.CANCELLED,
]

DASHBOARD_EXCLUDED_USERNAMES = {
    "admin",
    "mark",
}

DASHBOARD_WORK_DURATION_VALID_FROM = date(
    2026,
    8,
    18,
)


def dashboard_work_duration_cutoff():
    return timezone.make_aware(
        datetime.combine(
            DASHBOARD_WORK_DURATION_VALID_FROM,
            time.min,
        ),
        timezone.get_current_timezone(),
    )


def average_work_duration(queryset):
    durations = []
    cutoff = dashboard_work_duration_cutoff()

    rows = queryset.filter(
        status=Task.Status.DONE,
        started_at__gte=cutoff,
        completed_at__gte=cutoff,
    ).values_list(
        "started_at",
        "completed_at",
    )

    for started_at, completed_at in rows:
        if completed_at < started_at:
            continue

        durations.append(
            completed_at - started_at
        )

    if not durations:
        return "", 0

    average_seconds = (
        sum(
            duration.total_seconds()
            for duration in durations
        )
        / len(durations)
    )

    return (
        format_duration(
            timedelta(seconds=average_seconds)
        ),
        len(durations),
    )


def dashboard(request):
    if not request.employee.can_manage_tasks:
        return HttpResponseForbidden(
            "Дашборд доступен только руководителю "
            "и администратору."
        )

    now = timezone.now()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    tasks = Task.objects.all()

    open_tasks = tasks.exclude(
        status__in=DASHBOARD_TERMINAL_STATUSES,
    )

    team = {
        "total": tasks.count(),
        "open": open_tasks.count(),
        "in_progress": tasks.filter(
            status=Task.Status.IN_PROGRESS,
        ).count(),
        "review": tasks.filter(
            status=Task.Status.REVIEW,
        ).count(),
        "overdue": open_tasks.filter(
            due_at__lt=now,
        ).count(),
        "high_priority": open_tasks.filter(
            priority__in=[
                Task.Priority.P0,
                Task.Priority.P1,
            ],
        ).count(),
        "done_7": tasks.filter(
            status=Task.Status.DONE,
            completed_at__gte=week_ago,
        ).count(),
        "done_30": tasks.filter(
            status=Task.Status.DONE,
            completed_at__gte=month_ago,
        ).count(),
        "unassigned": open_tasks.filter(
            assignee__isnull=True,
        ).count(),
    }

    employees = (
        Employee.objects
        .filter(is_active=True)
        .exclude(
            username__in=DASHBOARD_EXCLUDED_USERNAMES,
        )
        .order_by(
            "display_name",
            "username",
        )
    )

    employee_rows = []

    for employee in employees:
        employee_tasks = Task.objects.filter(
            assignee=employee,
        )

        employee_open = employee_tasks.exclude(
            status__in=DASHBOARD_TERMINAL_STATUSES,
        )

        avg_work, avg_work_sample = (
            average_work_duration(employee_tasks)
        )

        employee_rows.append({
            "employee": employee,
            "open": employee_open.count(),
            "in_progress": employee_tasks.filter(
                status=Task.Status.IN_PROGRESS,
            ).count(),
            "review": employee_tasks.filter(
                status=Task.Status.REVIEW,
            ).count(),
            "overdue": employee_open.filter(
                due_at__lt=now,
            ).count(),
            "high_priority": employee_open.filter(
                priority__in=[
                    Task.Priority.P0,
                    Task.Priority.P1,
                ],
            ).count(),
            "done_7": employee_tasks.filter(
                status=Task.Status.DONE,
                completed_at__gte=week_ago,
            ).count(),
            "done_30": employee_tasks.filter(
                status=Task.Status.DONE,
                completed_at__gte=month_ago,
            ).count(),
            "avg_work": avg_work,
            "avg_work_sample": avg_work_sample,
        })

    return render(
        request,
        "tasks/dashboard.html",
        {
            "team": team,
            "employee_rows": employee_rows,
            "team_members": employees.count(),
            "generated_at": now,
        },
    )

def home(request):
    terminal_statuses = [
        Task.Status.DONE,
        Task.Status.CANCELLED,
    ]

    base_tasks = Task.objects.filter(
        assignee=request.employee,
    ).exclude(
        status__in=terminal_statuses,
    )

    tasks = base_tasks

    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    direction = request.GET.get("direction", "")
    overdue = request.GET.get("overdue", "")
    hide_review = request.GET.get("hide_review", "")
    sort = request.GET.get("sort", "priority")

    if query:
        tasks = tasks.filter(
            Q(code__icontains=query)
            | Q(title__icontains=query)
            | Q(reporter__icontains=query)
            | Q(direction__icontains=query)
        )

    if status:
        tasks = tasks.filter(status=status)

    if priority:
        tasks = tasks.filter(priority=priority)

    if direction:
        tasks = tasks.filter(direction=direction)

    if overdue == "1":
        tasks = tasks.filter(
            due_at__lt=timezone.now(),
        )

    if hide_review == "1":
        tasks = tasks.exclude(
            status=Task.Status.REVIEW,
        )

    if sort == "due":
        tasks = tasks.annotate(
            due_missing=Case(
                When(due_at__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        ).order_by(
            "due_missing",
            "due_at",
            "-created_at",
        )
    elif sort == "updated":
        tasks = tasks.order_by("-updated_at")
    elif sort == "created":
        tasks = tasks.order_by("-created_at")
    elif sort == "title":
        tasks = tasks.order_by("title", "code")
    else:
        sort = "priority"
        tasks = ordered(tasks)

    directions = (
        base_tasks
        .exclude(direction="")
        .order_by("direction")
        .values_list("direction", flat=True)
        .distinct()
    )

    open_statuses = [
        choice
        for choice in Task.Status.choices
        if choice[0] not in terminal_statuses
    ]

    return render(
        request,
        "tasks/home.html",
        {
            "tasks": tasks,
            "statuses": open_statuses,
            "priorities": Task.Priority.choices,
            "directions": directions,
            "query": query,
            "selected_status": status,
            "selected_priority": priority,
            "selected_direction": direction,
            "selected_overdue": overdue,
            "selected_hide_review": hide_review,
            "selected_sort": sort,
            "filters_active": any([
                query,
                status,
                priority,
                direction,
                overdue,
                hide_review,
                sort != "priority",
            ]),
            "saved_filters": saved_filters_for(
                request.employee,
                SavedTaskFilter.Scope.MY,
            ),
        },
    )


def all_tasks(request):
    tasks = Task.objects.select_related(
        "assignee",
        "created_by",
    )

    status = request.GET.get("status", "")
    priority = request.GET.get("priority", "")
    assignee = request.GET.get("assignee", "")
    query = request.GET.get("q", "").strip()

    if status:
        tasks = tasks.filter(status=status)

    if priority:
        tasks = tasks.filter(priority=priority)

    if assignee:
        tasks = tasks.filter(assignee_id=assignee)

    if query:
        tasks = tasks.filter(
            Q(code__icontains=query)
            | Q(title__icontains=query)
            | Q(reporter__icontains=query)
            | Q(direction__icontains=query)
        )

    tasks = ordered(tasks)

    return render(
        request,
        "tasks/all_tasks.html",
        {
            "tasks": tasks,
            "statuses": Task.Status.choices,
            "priorities": Task.Priority.choices,
            "employees": Employee.objects.filter(is_active=True),
            "saved_filters": saved_filters_for(
                request.employee,
                SavedTaskFilter.Scope.ALL,
            ),
            "filters_active": any([
                query,
                status,
                priority,
                assignee,
            ]),
        },
    )


def done_tasks(request):
    tasks = Task.objects.select_related(
        "assignee",
        "created_by",
    ).filter(
        status=Task.Status.DONE,
    )

    query = request.GET.get("q", "").strip()
    priority = request.GET.get("priority", "")
    assignee = request.GET.get("assignee", "")
    direction = request.GET.get("direction", "")
    completed_from = request.GET.get("completed_from", "")
    completed_to = request.GET.get("completed_to", "")

    if query:
        tasks = tasks.filter(
            Q(code__icontains=query)
            | Q(title__icontains=query)
            | Q(reporter__icontains=query)
            | Q(direction__icontains=query)
            | Q(completion_comment__icontains=query)
            | Q(completion_url__icontains=query)
        )

    if priority:
        tasks = tasks.filter(priority=priority)

    if assignee:
        tasks = tasks.filter(assignee_id=assignee)

    if direction:
        tasks = tasks.filter(direction=direction)

    date_from = parse_date(completed_from) if completed_from else None
    date_to = parse_date(completed_to) if completed_to else None

    if date_from:
        tasks = tasks.filter(completed_at__date__gte=date_from)

    if date_to:
        tasks = tasks.filter(completed_at__date__lte=date_to)

    tasks = tasks.order_by(
        "-completed_at",
        "-updated_at",
    )

    directions = (
        Task.objects
        .filter(status=Task.Status.DONE)
        .exclude(direction="")
        .order_by("direction")
        .values_list("direction", flat=True)
        .distinct()
    )

    return render(
        request,
        "tasks/done_tasks.html",
        {
            "tasks": tasks,
            "priorities": Task.Priority.choices,
            "employees": Employee.objects.filter(is_active=True),
            "directions": directions,
            "query": query,
            "selected_priority": priority,
            "selected_assignee": assignee,
            "selected_direction": direction,
            "selected_completed_from": completed_from,
            "selected_completed_to": completed_to,
        },
    )


def waiting_tasks(request):
    if not request.employee.can_manage_tasks:
        return HttpResponseForbidden(
            "Только руководитель может видеть очередь приоритизации."
        )

    tasks = ordered(
        Task.objects.filter(
            priority=Task.Priority.WAITING,
        ).exclude(
            status__in=[
                Task.Status.DONE,
                Task.Status.CANCELLED,
            ]
        )
    )

    return render(
        request,
        "tasks/all_tasks.html",
        {
            "tasks": tasks,
            "statuses": Task.Status.choices,
            "priorities": Task.Priority.choices,
            "employees": Employee.objects.filter(is_active=True),
            "page_title": "Ожидают оценки",
        },
    )


def task_create(request):
    if request.method == "POST":
        form = TaskCreateForm(request.POST)

        if form.is_valid():
            task = create_task(
                employee=request.employee,
                cleaned_data=form.cleaned_data,
            )

            return redirect(
                "task_detail",
                pk=task.pk,
            )
    else:
        form = TaskCreateForm(
            initial={
                "reporter": request.employee.display_name
                or request.employee.username,
            }
        )

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "page_title": "Новая задача",
        },
    )


def task_detail(request, pk):
    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "created_by",
        ),
        pk=pk,
    )

    history = task.history.select_related(
        "actor",
    )[:100]

    comments = task.comments.select_related(
        "author",
    ).all()

    from .forms import TaskCompletionForm

    can_complete = (
        task.status not in [
            Task.Status.DONE,
            Task.Status.CANCELLED,
        ]
        and (
            request.employee.can_manage_tasks
            or task.assignee_id == request.employee.id
        )
    )

    can_reopen = (
        task.status == Task.Status.DONE
        and (
            request.employee.can_manage_tasks
            or task.assignee_id == request.employee.id
        )
    )

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "history": history,
            **watcher_context(
                task,
                request.employee,
            ),
            "comments": comments,
            "comment_form": TaskCommentForm(),
            "can_complete": can_complete,
            "can_reopen": can_reopen,
            "completion_form": TaskCompletionForm(),
            "open_completion_dialog": (
                can_complete
                and request.GET.get("complete") == "1"
            ),
            "reopen_form": TaskReopenForm(
                initial={
                    "status": Task.Status.IN_PROGRESS,
                }
            ),
        },
    )




@transaction.atomic
def task_watcher_toggle(request, pk):
    task = get_object_or_404(
        Task,
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    existing = TaskWatcher.objects.filter(
        task=task,
        employee=request.employee,
    ).first()

    if existing:
        existing.delete()
    else:
        TaskWatcher.objects.create(
            task=task,
            employee=request.employee,
            added_by=request.employee,
        )

    return redirect(
        "task_detail",
        pk=task.pk,
    )


@transaction.atomic
def task_watcher_manage(request, pk):
    task = get_object_or_404(
        Task,
        pk=pk,
    )

    if not request.employee.can_manage_tasks:
        return HttpResponseForbidden(
            "Управлять наблюдателями может только руководитель."
        )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    employee_id = request.POST.get(
        "employee_id",
        "",
    ).strip()

    action = request.POST.get(
        "action",
        "",
    ).strip()

    if not employee_id:
        return HttpResponseBadRequest(
            "Не выбран сотрудник."
        )

    employee = get_object_or_404(
        Employee,
        pk=employee_id,
    )

    if action == "add":
        if not employee.is_active:
            return HttpResponseBadRequest(
                "Нельзя добавить неактивного сотрудника."
            )

        TaskWatcher.objects.get_or_create(
            task=task,
            employee=employee,
            defaults={
                "added_by": request.employee,
            },
        )

    elif action == "remove":
        TaskWatcher.objects.filter(
            task=task,
            employee=employee,
        ).delete()

    else:
        return HttpResponseBadRequest(
            "Недопустимое действие."
        )

    return redirect(
        "task_detail",
        pk=task.pk,
    )


@transaction.atomic
def task_comment_add(request, pk):
    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "created_by",
        ),
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    form = TaskCommentForm(request.POST)

    if form.is_valid():
        comment = TaskComment.objects.create(
            task=task,
            author=request.employee,
            body=form.cleaned_data["body"],
        )

        enqueue_comment(
            task=task,
            actor=request.employee,
            comment=comment,
        )

        return redirect(
            "task_detail",
            pk=task.pk,
        )

    history = task.history.select_related(
        "actor",
    )[:100]

    comments = task.comments.select_related(
        "author",
    ).all()

    from .forms import TaskCompletionForm

    can_complete = (
        task.status not in [
            Task.Status.DONE,
            Task.Status.CANCELLED,
        ]
        and (
            request.employee.can_manage_tasks
            or task.assignee_id == request.employee.id
        )
    )

    can_reopen = (
        task.status == Task.Status.DONE
        and (
            request.employee.can_manage_tasks
            or task.assignee_id == request.employee.id
        )
    )

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "history": history,
            **watcher_context(
                task,
                request.employee,
            ),
            "comments": comments,
            "comment_form": form,
            "can_complete": can_complete,
            "can_reopen": can_reopen,
            "completion_form": TaskCompletionForm(),
            "reopen_form": TaskReopenForm(
                initial={
                    "status": Task.Status.IN_PROGRESS,
                }
            ),
        },
        status=400,
    )


@transaction.atomic
def task_quick_status(request, pk):
    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "created_by",
            "reporter_employee",
        ),
        pk=pk,
    )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    allowed = (
        request.employee.can_manage_tasks
        or task.assignee_id == request.employee.id
    )

    if not allowed:
        return HttpResponseForbidden(
            "Менять статус можно только у своих задач."
        )

    if task.status in [
        Task.Status.DONE,
        Task.Status.CANCELLED,
    ]:
        return task_action_redirect(
            request,
            task,
        )

    target_status = request.POST.get(
        "status",
        "",
    )

    if target_status not in [
        Task.Status.IN_PROGRESS,
        Task.Status.REVIEW,
    ]:
        return HttpResponseBadRequest(
            "Недопустимый быстрый статус."
        )

    if (
        target_status == Task.Status.REVIEW
        and task.status not in [
            Task.Status.IN_PROGRESS,
            Task.Status.BLOCKED,
        ]
    ):
        return HttpResponseBadRequest(
            "На проверку можно отправить задачу "
            "из работы или блокировки."
        )

    if task.status == target_status:
        return task_action_redirect(
            request,
            task,
        )

    before = {
        "status": task.status,
        "started_at": task.started_at,
    }

    task.status = target_status

    if (
        target_status == Task.Status.IN_PROGRESS
        and not task.started_at
    ):
        task.started_at = timezone.now()

    task.save()

    record_changes(
        task=task,
        actor=request.employee,
        before=before,
        fields=[
            "status",
            "started_at",
        ],
    )

    enqueue_status_change(
        task=task,
        actor=request.employee,
        old_status=before["status"],
    )

    return task_action_redirect(
        request,
        task,
    )


@transaction.atomic
def task_reopen(request, pk):
    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "created_by",
            "reporter_employee",
        ),
        pk=pk,
    )

    allowed = (
        request.employee.can_manage_tasks
        or task.assignee_id == request.employee.id
    )

    if not allowed:
        return HttpResponseForbidden(
            "Повторно открывать можно только свои задачи."
        )

    if task.status != Task.Status.DONE:
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    form = TaskReopenForm(request.POST)

    if form.is_valid():
        before = {
            "status": task.status,
            "completed_at": task.completed_at,
        }

        task.status = form.cleaned_data["status"]
        task.completed_at = None

        # started_at intentionally remains unchanged:
        # it is the first factual start of this task.
        #
        # completion_comment and completion_url also remain:
        # the previous result must not be destroyed.
        task.save()

        record_changes(
            task=task,
            actor=request.employee,
            before=before,
            fields=[
                "status",
                "completed_at",
            ],
        )

        enqueue_status_change(
            task=task,
            actor=request.employee,
            old_status=before["status"],
        )

        return redirect(
            "task_detail",
            pk=task.pk,
        )

    history = task.history.select_related(
        "actor",
    )[:100]

    from .forms import TaskCompletionForm

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "history": history,
            **watcher_context(
                task,
                request.employee,
            ),
            "can_complete": False,
            "can_reopen": True,
            "completion_form": TaskCompletionForm(),
            "reopen_form": form,
            "open_reopen_dialog": True,
        },
        status=400,
    )


@transaction.atomic
def task_complete(request, pk):
    from .forms import TaskCompletionForm

    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "created_by",
            "reporter_employee",
        ),
        pk=pk,
    )

    allowed = (
        request.employee.can_manage_tasks
        or task.assignee_id == request.employee.id
    )

    if not allowed:
        return HttpResponseForbidden(
            "Завершать можно только свои задачи."
        )

    if task.status in [
        Task.Status.DONE,
        Task.Status.CANCELLED,
    ]:
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    if request.method != "POST":
        return redirect(
            "task_detail",
            pk=task.pk,
        )

    form = TaskCompletionForm(request.POST)

    if form.is_valid():
        before = {
            "status": task.status,
            "completion_comment": task.completion_comment,
            "completion_url": task.completion_url,
            "completed_at": task.completed_at,
        }

        task.status = form.cleaned_data["status"]
        task.completion_comment = form.cleaned_data["result"]
        task.completion_url = form.cleaned_data["result_url"]
        task.completed_at = timezone.now()
        task.save()

        record_changes(
            task=task,
            actor=request.employee,
            before=before,
            fields=[
                "status",
                "completion_comment",
                "completion_url",
                "completed_at",
            ],
        )

        enqueue_completion(
            task=task,
            actor=request.employee,
            old_status=before["status"],
        )

        return redirect(
            "task_detail",
            pk=task.pk,
        )

    history = task.history.select_related(
        "actor",
    )[:100]

    return render(
        request,
        "tasks/task_detail.html",
        {
            "task": task,
            "history": history,
            **watcher_context(
                task,
                request.employee,
            ),
            "can_complete": True,
            "completion_form": form,
            "open_completion_dialog": True,
        },
        status=400,
    )


@transaction.atomic
def task_edit(request, pk):
    task = get_object_or_404(
        Task.objects.select_related(
            "assignee",
            "reporter_employee",
        ),
        pk=pk,
    )

    if not request.employee.can_manage_tasks:
        if task.assignee_id != request.employee.id:
            return HttpResponseForbidden(
                "Редактировать можно только свои задачи."
            )

        form_class = MemberTaskUpdateForm
        tracked_fields = [
            "status",
            "next_step",
            "blockers",
            "materials_url",
        ]
    else:
        form_class = ManagerTaskUpdateForm
        tracked_fields = [
            "title",
            "acceptance_criteria",
            "reporter",
            "direction",
            "assignee_id",
            "priority",
            "status",
            "due_at",
            "estimate_hours",
            "blockers",
            "next_step",
            "materials_url",
        ]

    before = {
        field: (
            task.assignee_id
            if field == "assignee_id"
            else getattr(task, field)
        )
        for field in tracked_fields
    }

    before["started_at"] = task.started_at

    if request.method == "POST":
        form = form_class(
            request.POST,
            instance=task,
        )

        if form.is_valid():
            task = form.save(commit=False)

            if (
                task.status == Task.Status.IN_PROGRESS
                and not task.started_at
            ):
                task.started_at = timezone.now()

            if task.status in [
                Task.Status.DONE,
                Task.Status.CANCELLED,
            ]:
                if not task.completed_at:
                    task.completed_at = timezone.now()
            else:
                task.completed_at = None

            task.save()

            record_changes(
                task=task,
                actor=request.employee,
                before=before,
                fields=tracked_fields + ["started_at"],
            )

            enqueue_assignment(
                task=task,
                actor=request.employee,
                previous_assignee_id=before.get(
                    "assignee_id"
                ),
            )

            enqueue_status_change(
                task=task,
                actor=request.employee,
                old_status=before.get(
                    "status"
                ),
            )

            return redirect(
                "task_detail",
                pk=task.pk,
            )
    else:
        form = form_class(instance=task)

    return render(
        request,
        "tasks/task_form.html",
        {
            "form": form,
            "task": task,
            "page_title": f"Редактирование {task.code}",
        },
    )

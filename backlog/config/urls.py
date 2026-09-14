from django.urls import path

from tasks import views


urlpatterns = [
    path("healthz/", views.healthz, name="healthz"),

    path("", views.home, name="home"),
    path("tasks/", views.all_tasks, name="all_tasks"),
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),
    path("tasks/done/", views.done_tasks, name="done_tasks"),
    path("tasks/new/", views.task_create, name="task_create"),
    path(
        "telegram/link/<str:token>/",
        views.telegram_link,
        name="telegram_link",
    ),
    path(
        "tasks/waiting/",
        views.waiting_tasks,
        name="waiting_tasks",
    ),
    path(
        "tasks/<int:pk>/",
        views.task_detail,
        name="task_detail",
    ),
    path(
        "tasks/<int:pk>/complete/",
        views.task_complete,
        name="task_complete",
    ),
    path(
        "tasks/<int:pk>/comments/",
        views.task_comment_add,
        name="task_comment_add",
    ),
    path(
        "filters/save/",
        views.saved_filter_create,
        name="saved_filter_create",
    ),
    path(
        "filters/<int:pk>/apply/",
        views.saved_filter_apply,
        name="saved_filter_apply",
    ),
    path(
        "filters/<int:pk>/delete/",
        views.saved_filter_delete,
        name="saved_filter_delete",
    ),
    path(
        "tasks/<int:pk>/watch/",
        views.task_watcher_toggle,
        name="task_watcher_toggle",
    ),
    path(
        "tasks/<int:pk>/watchers/",
        views.task_watcher_manage,
        name="task_watcher_manage",
    ),
    path(
        "tasks/<int:pk>/quick-status/",
        views.task_quick_status,
        name="task_quick_status",
    ),
    path(
        "tasks/<int:pk>/reopen/",
        views.task_reopen,
        name="task_reopen",
    ),
    path(
        "tasks/<int:pk>/edit/",
        views.task_edit,
        name="task_edit",
    ),
]

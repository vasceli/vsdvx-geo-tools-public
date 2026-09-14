from django.contrib import admin
from django.urls import path

from . import views


urlpatterns = [
    path(
        "",
        views.dashboard,
        name="dashboard",
    ),
    path(
        "login/",
        views.EmployeeLoginView.as_view(),
        name="login",
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout",
    ),
    path(
        "password/change-required/",
        views.password_change_required,
        name="password_change_required",
    ),
    path(
        "auth/check/",
        views.auth_check,
        name="auth_check",
    ),
    path(
        "admin/",
        admin.site.urls,
    ),
]

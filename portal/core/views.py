from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.views import LoginView
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


MUST_CHANGE_PASSWORD_GROUP = "must_change_password"  # pragma: allowlist secret

APP_ACCESS_GROUPS = {
    "utm.example.com": "app_utmgenerator",
    "contracts.example.com": "app_contractgenerator",
}


def must_change_password(user):
    return (
        user.is_authenticated
        and user.groups.filter(
            name=MUST_CHANGE_PASSWORD_GROUP
        ).exists()
    )


def safe_next_url(request):
    value = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    )

    if value and url_has_allowed_host_and_scheme(
        value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value

    return settings.LOGIN_REDIRECT_URL


def password_change_url(next_url):
    base = reverse("password_change_required")

    if not next_url:
        return base

    return f"{base}?{urlencode({'next': next_url})}"


class EmployeeLoginView(LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self):
        next_url = (
            self.get_redirect_url()
            or settings.LOGIN_REDIRECT_URL
        )

        if must_change_password(self.request.user):
            return password_change_url(next_url)

        return next_url


@login_required
def dashboard(request):
    if must_change_password(request.user):
        return redirect(
            password_change_url("/")
        )

    return render(request, "dashboard.html")


def auth_check(request):
    user = request.user

    if (
        not user.is_authenticated
        or not user.is_active
        or must_change_password(user)
    ):
        return HttpResponse(status=401)

    host = request.get_host().split(":", 1)[0].lower()
    required_group = APP_ACCESS_GROUPS.get(host)

    # Preserve the existing behavior for internal/unknown hosts.
    # Known public applications are explicitly access-controlled.
    if (
        required_group
        and not user.is_superuser
        and not user.groups.filter(name=required_group).exists()
    ):
        return HttpResponse(status=403)

    response = HttpResponse(status=204)
    response["X-Auth-User"] = user.get_username()
    return response


@login_required
def password_change_required(request):
    next_url = safe_next_url(request)

    if not must_change_password(request.user):
        return redirect(next_url)

    if request.method == "POST":
        form = PasswordChangeForm(
            request.user,
            request.POST,
        )

        if form.is_valid():
            user = form.save()

            update_session_auth_hash(
                request,
                user,
            )

            group = user.groups.filter(
                name=MUST_CHANGE_PASSWORD_GROUP
            ).first()

            if group:
                user.groups.remove(group)

            return redirect(next_url)
    else:
        form = PasswordChangeForm(request.user)

    return render(
        request,
        "registration/password_change_required.html",
        {
            "form": form,
            "next": next_url,
        },
    )


def logout_view(request):
    logout(request)
    return redirect("login")

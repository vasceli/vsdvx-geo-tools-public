from django.http import HttpResponseForbidden

from .models import Employee


class AuthUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == "/healthz/":
            return self.get_response(request)

        username = request.META.get("HTTP_X_AUTH_USER", "").strip()

        if not username:
            return HttpResponseForbidden("Missing authenticated identity")

        employee, _ = Employee.objects.get_or_create(
            username=username,
            defaults={
                "display_name": username,
                "role": Employee.Role.MEMBER,
            },
        )

        if not employee.is_active:
            return HttpResponseForbidden("Backlog user disabled")

        request.employee = employee

        return self.get_response(request)

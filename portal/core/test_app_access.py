from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase


class ApplicationAccessTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

        self.user = self.User.objects.create_user(
            username="employee",
            password="test-password-123",  # pragma: allowlist secret
        )

        self.utm_group = Group.objects.create(
            name="app_utmgenerator",
        )

        self.contract_group = Group.objects.create(
            name="app_contractgenerator",
        )

    def auth_check(self, host):
        return self.client.get(
            "/auth/check/",
            HTTP_HOST=host,
        )

    def test_utm_user_is_allowed_to_utm(self):
        self.user.groups.add(self.utm_group)
        self.client.force_login(self.user)

        response = self.auth_check(
            "utm.example.com",
        )

        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            response["X-Auth-User"],
            "employee",
        )

    def test_user_without_utm_group_gets_403(self):
        self.client.force_login(self.user)

        response = self.auth_check(
            "utm.example.com",
        )

        self.assertEqual(response.status_code, 403)

    def test_contract_user_is_allowed_to_contract(self):
        self.user.groups.add(self.contract_group)
        self.client.force_login(self.user)

        response = self.auth_check(
            "contracts.example.com",
        )

        self.assertEqual(response.status_code, 204)

    def test_utm_only_user_cannot_access_contract(self):
        self.user.groups.add(self.utm_group)
        self.client.force_login(self.user)

        response = self.auth_check(
            "contracts.example.com",
        )

        self.assertEqual(response.status_code, 403)

    def test_contract_only_user_cannot_access_utm(self):
        self.user.groups.add(self.contract_group)
        self.client.force_login(self.user)

        response = self.auth_check(
            "utm.example.com",
        )

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_access_both_apps(self):
        admin = self.User.objects.create_superuser(
            username="access-admin",
            email="admin@example.invalid",
            password="test-password-123",  # pragma: allowlist secret
        )

        self.client.force_login(admin)

        self.assertEqual(
            self.auth_check(
                "utm.example.com",
            ).status_code,
            204,
        )

        self.assertEqual(
            self.auth_check(
                "contracts.example.com",
            ).status_code,
            204,
        )

    def test_unknown_host_keeps_legacy_behavior(self):
        self.client.force_login(self.user)

        response = self.auth_check(
            "testserver",
        )

        self.assertEqual(response.status_code, 204)

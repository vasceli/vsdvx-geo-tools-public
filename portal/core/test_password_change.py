from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase


User = get_user_model()


class ForcedPasswordChangeTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(
            name="must_change_password",
        )

        self.user = User.objects.create_user(
            username="worker",
            password="Temporary-2026!",  # pragma: allowlist secret
        )

        self.user.groups.add(self.group)

    def test_temporary_user_is_rejected_by_auth_check(self):
        self.client.force_login(self.user)

        response = self.client.get(
            "/auth/check/",
        )

        self.assertEqual(
            response.status_code,
            401,
        )

    def test_login_redirects_to_password_change(self):
        response = self.client.post(
            "/login/?next=/",
            {
                "username": "worker",
                "password": "Temporary-2026!",  # pragma: allowlist secret
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.assertIn(
            "/password/change-required/",
            response["Location"],
        )

    def test_password_change_unlocks_account(self):
        self.client.force_login(self.user)

        response = self.client.post(
            "/password/change-required/",
            {
                "old_password": "Temporary-2026!",  # pragma: allowlist secret
                "new_password1": "Permanent-2026-Strong!",  # pragma: allowlist secret
                "new_password2": "Permanent-2026-Strong!",  # pragma: allowlist secret
                "next": "/",
            },
        )

        self.assertEqual(
            response.status_code,
            302,
        )

        self.user.refresh_from_db()

        self.assertTrue(
            self.user.check_password(
                "Permanent-2026-Strong!"
            )
        )

        self.assertFalse(
            self.user.groups.filter(
                name="must_change_password",
            ).exists()
        )

        response = self.client.get(
            "/auth/check/",
        )

        self.assertEqual(
            response.status_code,
            204,
        )

        self.assertEqual(
            response["X-Auth-User"],
            "worker",
        )

    def test_normal_user_is_not_blocked(self):
        normal = User.objects.create_user(
            username="normal",
            password="Normal-2026-Strong!",  # pragma: allowlist secret
        )

        self.client.force_login(normal)

        response = self.client.get(
            "/auth/check/",
        )

        self.assertEqual(
            response.status_code,
            204,
        )

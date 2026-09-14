from django.contrib.auth import get_user_model
from django.test import TestCase


class AuthCheckTests(TestCase):
    def test_anonymous_user_gets_401(self):
        response = self.client.get("/auth/check/")
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("X-Auth-User", response)

    def test_active_authenticated_user_gets_identity_header(self):
        user = get_user_model().objects.create_user(
            username="testuser",
            password="test-password",  # pragma: allowlist secret
            is_active=True,
        )
        self.client.force_login(user)

        response = self.client.get("/auth/check/")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["X-Auth-User"], "testuser")

    def test_inactive_user_gets_401(self):
        user = get_user_model().objects.create_user(
            username="inactive",
            password="test-password",  # pragma: allowlist secret
            is_active=False,
        )
        self.client.force_login(user)

        response = self.client.get("/auth/check/")

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("X-Auth-User", response)

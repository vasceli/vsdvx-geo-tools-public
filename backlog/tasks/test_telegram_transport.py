import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from tasks import telegram


class TelegramTransportTests(SimpleTestCase):
    def tearDown(self):
        telegram._SESSION = None

    @patch("tasks.telegram.requests.Session")
    def test_session_uses_socks_proxy(self, session_class):
        session = Mock()
        session_class.return_value = session

        with patch.dict(
            os.environ,
            {
                "TELEGRAM_PROXY_URL":
                    "socks5h://127.0.0.1:1080"
            },
        ):
            result = telegram.telegram_session()

        self.assertIs(result, session)
        self.assertFalse(session.trust_env)

        session.proxies.update.assert_called_once_with({
            "http": "socks5h://127.0.0.1:1080",
            "https": "socks5h://127.0.0.1:1080",
        })

    @patch("tasks.telegram.telegram_session")
    def test_api_uses_connect_and_read_timeout(
        self,
        telegram_session,
    ):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "ok": True,
            "result": {"id": 1},
        }

        session = Mock()
        session.post.return_value = response
        telegram_session.return_value = session

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "test-token"},
        ):
            result = telegram.telegram_api(
                "getMe",
                timeout=7,
            )

        self.assertEqual(result, {"id": 1})

        self.assertEqual(
            session.post.call_args.kwargs["timeout"],
            (5, 7),
        )

# Backlog service

Internal Django workflow service for tasks, assignments, status, comments, completion evidence, saved filters, watchers, and durable notifications.

The application expects identity to be supplied by the authenticated reverse-proxy boundary. `BACKLOG_SECRET_KEY` is mandatory. Telegram is optional and requires an external `TELEGRAM_BOT_TOKEN`; no working token, user ID, chat ID, or proxy credential is included.

Run tests from this directory after installing `requirements.txt`:

```bash
BACKLOG_SECRET_KEY=test-only python manage.py test
```

All test users and task data are synthetic.

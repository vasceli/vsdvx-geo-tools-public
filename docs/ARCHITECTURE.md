# Architecture

All public hostnames below are reserved examples and do not describe a live deployment.

| Component | Runtime | Example binding | Responsibility |
|---|---|---:|---|
| Nginx | system service | `0.0.0.0:443` | TLS, routing, and subrequest authorization |
| Auth portal | Django/Gunicorn | `127.0.0.1:8000` | Login, sessions, groups, password policy |
| Contract service | FastAPI/Uvicorn | `127.0.0.1:8765` | Calculations, parsing, document rendering |
| Backlog | Django/Gunicorn | `127.0.0.1:5090` | Tasks, comments, watchers, notification outbox |

## Authorization flow

1. A browser requests `https://contracts.example.com/` or `https://backlog.example.com/`.
2. Nginx sends an internal subrequest to the portal's `/auth/check/` endpoint.
3. The portal validates the signed Django session and the hostname-to-group mapping.
4. Nginx proxies authorized traffic to the loopback application; unauthorized users are redirected to the portal.

## State boundaries

- Source control contains code and synthetic fixtures only.
- Portal and backlog SQLite databases are runtime state.
- Generated contracts, uploaded requisites, exports, logs, and Telegram identifiers are runtime/private data.
- Environment files and any proxy credentials are managed outside Git.

## Notification flow

Backlog domain events create outbox rows in the same database transaction as the task update. A separate notifier claims pending rows, delivers them through the configured transport, and records retry state. Telegram is optional and the code accepts a proxy URL only from the environment; no live proxy topology is documented here.

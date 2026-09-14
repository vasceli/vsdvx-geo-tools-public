# Generic operations guide

This is a safe portfolio runbook, not a production recovery procedure.

## Pre-deployment gates

1. Run unit tests and dedicated secret/PII scans.
2. Replace all `.env.example` placeholders in a protected secret store.
3. Confirm Django checks pass with `DEBUG=False`.
4. Validate `nginx -t` against the adapted example configuration.
5. Confirm every application binds to loopback.
6. Apply database migrations and back up existing runtime state through a separately controlled process.

## Health checks

```bash
curl -fsS http://127.0.0.1:8000/login/ >/dev/null
curl -fsS http://127.0.0.1:8765/api/health
curl -fsS http://127.0.0.1:5090/healthz/
```

## Deployment evidence

Record version, migration output, configuration validation, service status, health responses, and rollback point. Store that evidence outside the public repository because logs can contain user identifiers and internal paths.

## Recovery

Restore databases and secret files only from an approved encrypted backup. Validate ownership and permissions, run integrity checks, rotate compromised credentials when required, and verify authorization before reopening public traffic.

#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:8000/login/ >/dev/null && echo 'portal: OK'
curl -fsS http://127.0.0.1:8765/api/health && echo
curl -fsS http://127.0.0.1:5090/healthz/ >/dev/null && echo 'backlog: OK'

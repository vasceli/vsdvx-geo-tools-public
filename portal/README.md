# Authentication portal

Django session and group gateway used with Nginx `auth_request`. It implements login, logout, a mandatory first-password-change group, safe return URLs, and hostname-to-access-group mapping.

`DJANGO_SECRET_KEY` is mandatory. Example hostnames use the reserved `example.com` domain.

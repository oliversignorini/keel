"""The dedicated ASGI stream service's entrypoint (PRD §4 system
architecture: "same image, separate service. SSE only.
Proxy buffering OFF.").

Run with ``uvicorn config.asgi_stream:application`` — never gunicorn:
the whole point of this second service is that SSE's held-open
connections must not occupy the sync worker pool that serves ordinary
request/response traffic.

Same settings module and same Django app registry as ``config.asgi`` /
``config.wsgi`` — only ``ROOT_URLCONF`` differs, swapped to
``config.urls_stream`` below before the ASGI application is built, so
this process only ever resolves the one route it exists to serve.
"""

import os

import django
from django.conf import settings

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
django.setup()
settings.ROOT_URLCONF = "config.urls_stream"

from django.core.asgi import get_asgi_application  # noqa: E402

application = get_asgi_application()

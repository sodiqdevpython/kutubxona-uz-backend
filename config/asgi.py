"""
ASGI konfiguratsiyasi — HTTP + WebSocket.

HTTP so'rovlar odatdagidek Django'ga, `ws://…/ws/…` esa Channels
consumer'lariga boradi (real-time chat). Ishga tushirish:

    uvicorn config.asgi:application --host 0.0.0.0 --port 8000
    # yoki
    daphne -b 0.0.0.0 -p 8000 config.asgi:application
"""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.asgi import get_asgi_application

# Django app registry WebSocket importlaridan OLDIN yuklanishi shart
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter        # noqa: E402
from channels.security.websocket import OriginValidator           # noqa: E402
from django.conf import settings                                  # noqa: E402

from apps.chat.auth import JWTAuthMiddleware                      # noqa: E402
from apps.chat.routing import websocket_urlpatterns               # noqa: E402

_ws_app = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))

# WS_ALLOWED_ORIGINS='*' bo'lsa — hech qanday cheklov qo'ymaymiz (dev).
# Aks holda faqat ro'yxatdagi originlar ulana oladi (production).
_allowed_origins = getattr(settings, 'WS_ALLOWED_ORIGINS', ['*'])
if '*' not in _allowed_origins:
    _ws_app = OriginValidator(_ws_app, _allowed_origins)

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': _ws_app,
})

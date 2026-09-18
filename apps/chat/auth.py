"""
WebSocket uchun JWT autentifikatsiya middleware.

Brauzer WebSocket API'si header qo'sha olmaydi, shuning uchun token
query-string orqali uzatiladi:  ws://…/ws/admin/chat/?token=<access>

Token yaroqsiz bo'lsa — scope['user'] = AnonymousUser, consumer ulanishni yopadi.
"""
import logging
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


@database_sync_to_async
def _user_from_token(raw_token: str):
    from rest_framework_simplejwt.authentication import JWTAuthentication
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

    auth = JWTAuthentication()
    try:
        validated = auth.get_validated_token(raw_token)
        return auth.get_user(validated)
    except (InvalidToken, TokenError, Exception) as exc:
        logger.info('WS token yaroqsiz: %s', exc)
        return AnonymousUser()


class JWTAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        token = ''
        qs = parse_qs((scope.get('query_string') or b'').decode())
        if qs.get('token'):
            token = qs['token'][0]

        if not token:
            # Ixtiyoriy: Sec-WebSocket-Protocol orqali ham qabul qilamiz
            for name, value in scope.get('headers', []):
                if name == b'sec-websocket-protocol':
                    parts = [p.strip() for p in value.decode().split(',')]
                    if len(parts) == 2 and parts[0] == 'jwt':
                        token = parts[1]
                    break

        scope['user'] = await _user_from_token(token) if token else AnonymousUser()
        return await super().__call__(scope, receive, send)

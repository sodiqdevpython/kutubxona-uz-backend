"""
Hamkor API autentifikatsiyasi: `Authorization: Bearer <partner access token>`.

Token Django foydalanuvchisiga emas, `PartnerClient` ga bog'langan, shuning
uchun `request.user` o'rniga yengil `PartnerIdentity` obyekti qo'yiladi.
"""
import logging

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework_simplejwt.exceptions import TokenError

from .models import PartnerClient
from .tokens import PartnerAccessToken

logger = logging.getLogger(__name__)


class PartnerIdentity:
    """DRF `request.user` o'rnini bosuvchi minimal obyekt."""

    is_authenticated = True
    is_staff         = False
    is_superuser     = False
    is_anonymous     = False

    def __init__(self, client: PartnerClient):
        self.client = client
        self.pk     = client.pk
        self.id     = client.pk

    def __str__(self):
        return f'partner:{self.client.client_id}'


class PartnerJWTAuthentication(BaseAuthentication):
    keyword = b'bearer'

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword:
            return None                       # boshqa autentifikatsiyaga yo'l beramiz
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed('Authorization sarlavhasi noto\'g\'ri')

        raw = parts[1].decode()
        try:
            token = PartnerAccessToken(raw)
        except TokenError:
            raise exceptions.AuthenticationFailed('Token yaroqsiz yoki muddati tugagan')

        client_id = token.get('client_id')
        if not client_id:
            raise exceptions.AuthenticationFailed('Token tarkibi noto\'g\'ri')

        try:
            client = PartnerClient.objects.get(pk=client_id, is_active=True)
        except (PartnerClient.DoesNotExist, ValueError, TypeError):
            raise exceptions.AuthenticationFailed('Mijoz topilmadi yoki o\'chirilgan')

        # Token bekor qilinganmi? (admin «Tokenlarni bekor qilish» bosgan bo'lsa)
        if int(token.get('tv') or 1) != int(client.token_version or 1):
            raise exceptions.AuthenticationFailed('Token bekor qilingan')

        client.touch()
        return (PartnerIdentity(client), token)

    def authenticate_header(self, request):
        return 'Bearer realm="partner-api"'

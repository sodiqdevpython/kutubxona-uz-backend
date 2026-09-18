"""
Hamkor API uchun access/refresh tokenlar.

SimpleJWT infratuzilmasidan foydalanamiz, lekin tokenlar Django
foydalanuvchisiga emas, `PartnerClient` ga bog'lanadi:

  • `token_type` alohida ('partner_access' / 'partner_refresh') — shu sababli
    hamkor tokeni admin panel endpointlarida ishlamaydi va aksincha;
  • `user_id` claim'i yo'q — standart `JWTAuthentication` bu tokenni rad etadi.

Muddatlar `.env` orqali sozlanadi:
  PARTNER_ACCESS_LIFETIME_MIN   (standart 60 daqiqa)
  PARTNER_REFRESH_LIFETIME_DAYS (standart 30 kun)
"""
from django.conf import settings
from rest_framework_simplejwt.tokens import Token


class PartnerAccessToken(Token):
    token_type = 'partner_access'
    lifetime   = settings.PARTNER_ACCESS_LIFETIME


class PartnerRefreshToken(Token):
    token_type = 'partner_refresh'
    lifetime   = settings.PARTNER_REFRESH_LIFETIME

    @classmethod
    def for_client(cls, client) -> 'PartnerRefreshToken':
        token = cls()
        token['client_id'] = str(client.pk)
        # Token versiyasi — bekor qilish uchun (client.revoke_tokens())
        token['tv'] = client.token_version or 1
        return token

    def access_token(self) -> PartnerAccessToken:
        access = PartnerAccessToken()
        access.set_exp(from_time=access.current_time)
        access['client_id'] = self['client_id']
        access['tv']        = self.get('tv', 1)
        return access


def issue_pair(client) -> dict:
    """Yangi access + refresh juftligini qaytaradi."""
    refresh = PartnerRefreshToken.for_client(client)
    access  = refresh.access_token()
    return {
        'token_type':         'Bearer',
        'access':             str(access),
        'refresh':            str(refresh),
        'access_expires_in':  int(settings.PARTNER_ACCESS_LIFETIME.total_seconds()),
        'refresh_expires_in': int(settings.PARTNER_REFRESH_LIFETIME.total_seconds()),
    }

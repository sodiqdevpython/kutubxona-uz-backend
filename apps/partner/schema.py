"""drf-spectacular uchun hamkor autentifikatsiyasi kengaytmasi."""
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class PartnerJWTScheme(OpenApiAuthenticationExtension):
    target_class = 'apps.partner.authentication.PartnerJWTAuthentication'
    name         = 'partnerAuth'

    def get_security_definition(self, auto_schema):
        return {
            'type':         'http',
            'scheme':       'bearer',
            'bearerFormat': 'JWT',
            'description': (
                "`POST /api/partner/auth/token/` dan olingan access token.\n\n"
                "Misol: `Authorization: Bearer eyJhbGciOi…`"
            ),
        }

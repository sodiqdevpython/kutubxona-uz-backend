"""Hamkor API uchun kichik yordamchilar."""
from django.conf import settings


def partner_api_base(request=None) -> str:
    """
    Hamkorga beriladigan bazaviy manzil.

    Ustuvorlik:
      1) settings.PARTNER_API_BASE_URL  (.env → PARTNER_API_BASE_URL)
      2) so'rov kelgan manzil (masalan, admin panel qaysi domenda ochilgan bo'lsa)
      3) https://plagiat.journalkutubxona.uz
    """
    configured = (getattr(settings, 'PARTNER_API_BASE_URL', '') or '').strip().rstrip('/')
    if configured:
        return configured
    if request is not None:
        return f'{request.scheme}://{request.get_host()}'
    return 'https://plagiat.journalkutubxona.uz'

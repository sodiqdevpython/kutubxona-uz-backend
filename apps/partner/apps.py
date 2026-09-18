from django.apps import AppConfig


class PartnerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.partner'
    verbose_name = 'Hamkor API'

    def ready(self):
        # drf-spectacular autentifikatsiya kengaytmasini ro'yxatdan o'tkazamiz
        from . import schema  # noqa: F401

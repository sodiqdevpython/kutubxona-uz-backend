from django.apps import AppConfig


class ArticlesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.articles'
    verbose_name = 'Maqolalar'

    def ready(self):
        # Kontent o'zgarganda Redis keshini bekor qiluvchi signallar
        from utils.cache import register_invalidation
        register_invalidation()

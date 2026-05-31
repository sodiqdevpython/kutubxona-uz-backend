from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, ArticleViewSet

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('articles',   ArticleViewSet,  basename='article')

urlpatterns = router.urls

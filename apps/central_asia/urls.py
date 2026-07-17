from rest_framework.routers import DefaultRouter

from .views import CentralAsiaPostViewSet


router = DefaultRouter()
router.register('central-asia', CentralAsiaPostViewSet, basename='central-asia')

urlpatterns = router.urls

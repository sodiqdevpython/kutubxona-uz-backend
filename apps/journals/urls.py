from rest_framework.routers import DefaultRouter
from .views import JournalViewSet, IssueViewSet

router = DefaultRouter()
router.register('journals', JournalViewSet, basename='journal')
router.register('issues',   IssueViewSet,   basename='issue')

urlpatterns = router.urls

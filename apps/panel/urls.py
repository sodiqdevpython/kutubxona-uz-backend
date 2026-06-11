from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('auth/login/',   views.AdminLoginView.as_view(),   name='admin-login'),
    path('auth/refresh/', TokenRefreshView.as_view(),        name='admin-refresh'),
    path('auth/me/',      views.CurrentUserView.as_view(),   name='admin-me'),

    # ── Mualliflar ────────────────────────────────────────────────────────────
    path('authors/',          views.AdminAuthorListView.as_view(),   name='admin-author-list'),
    path('authors/<uuid:pk>/', views.AdminAuthorDetailView.as_view(), name='admin-author-detail'),

    # ── Topshirishlar ─────────────────────────────────────────────────────────
    path('submissions/',                      views.AdminSubmissionListView.as_view(),      name='admin-sub-list'),
    path('submissions/<uuid:pk>/',            views.AdminSubmissionUpdateView.as_view(),    name='admin-sub-update'),
    path('submissions/<uuid:pk>/ai-extract/', views.AdminSubmissionAIExtractView.as_view(), name='admin-sub-ai'),
    path('submissions/<uuid:pk>/approve/',    views.AdminSubmissionApproveView.as_view(),   name='admin-sub-approve'),
    path('submissions/<uuid:pk>/reject/',     views.AdminSubmissionRejectView.as_view(),    name='admin-sub-reject'),
    path('submissions/<uuid:pk>/revert/',     views.AdminSubmissionRevertView.as_view(),    name='admin-sub-revert'),

    # ── Yo'nalishlar ──────────────────────────────────────────────────────────
    path('categories/', views.AdminCategoryListView.as_view(), name='admin-category-list'),

    # ── Maqola AI (o'qitish / o'chirish) ─────────────────────────────────────
    path('articles/<uuid:pk>/train-ai/', views.AdminArticleTrainAIView.as_view(), name='admin-article-train-ai'),

    # ── Jurnal sonlari ────────────────────────────────────────────────────────
    path('journals/',     views.AdminJournalListView.as_view(), name='admin-journal-list'),
    path('issues/',       views.AdminIssueListView.as_view(),   name='admin-issue-list'),
    path('issues/<uuid:pk>/',                          views.AdminIssueDetailView.as_view(),        name='admin-issue-detail'),
    path('issues/<uuid:pk>/assign/',                   views.AdminIssueAssignArticleView.as_view(), name='admin-issue-assign'),
    path('issues/<uuid:pk>/articles/<uuid:article_id>/', views.AdminIssueRemoveArticleView.as_view(), name='admin-issue-remove'),
]

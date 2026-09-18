from django.urls import path

from . import docs, views

urlpatterns = [
    # Hamkorlar uchun hujjat sahifasi — client_id/client_secret bilan kiriladi
    path('docs/',        docs.PartnerDocsView.as_view(),       name='partner-docs'),
    path('docs/login/',  docs.PartnerDocsLoginView.as_view(),  name='partner-docs-login'),
    path('docs/logout/', docs.PartnerDocsLogoutView.as_view(), name='partner-docs-logout'),

    # Autentifikatsiya
    path('auth/token/',   views.PartnerTokenView.as_view(),        name='partner-token'),
    path('auth/refresh/', views.PartnerTokenRefreshView.as_view(), name='partner-token-refresh'),

    # Maqolalar — id (UUID) bo'yicha; fayl manzili oxirida fayl nomi bo'lishi mumkin
    path('articles/',                                views.PartnerArticleListView.as_view(),   name='partner-article-list'),
    path('articles/<uuid:pk>/',                      views.PartnerArticleDetailView.as_view(), name='partner-article-detail'),
    path('articles/<uuid:pk>/file/',                 views.PartnerArticleFileView.as_view(),   name='partner-article-file'),
    path('articles/<uuid:pk>/file/<str:filename>',   views.PartnerArticleFileView.as_view(),   name='partner-article-file-named'),
]

from django.urls import path

from . import views

urlpatterns = [
    # Autentifikatsiya
    path('auth/token/',   views.PartnerTokenView.as_view(),        name='partner-token'),
    path('auth/refresh/', views.PartnerTokenRefreshView.as_view(), name='partner-token-refresh'),

    # Maqolalar
    path('articles/',                   views.PartnerArticleListView.as_view(),   name='partner-article-list'),
    path('articles/<slug:slug>/',       views.PartnerArticleDetailView.as_view(), name='partner-article-detail'),
    path('articles/<slug:slug>/file/',  views.PartnerArticleFileView.as_view(),   name='partner-article-file'),
]

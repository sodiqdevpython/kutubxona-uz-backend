"""
Hamkor hujjati uchun cheklangan URL to'plami — sxema faqat shu yo'llardan
quriladi (keyin `keep_docs_paths` hook'i 3 ta endpointni qoldiradi).
"""
from django.urls import include, path

urlpatterns = [
    path('api/partner/', include('apps.partner.urls')),
]

"""
Hamkor hujjati uchun cheklangan URL to'plami — sxemaga faqat shu yo'llar tushadi.
(docs/* yo'llari oddiy Django view'lar, drf-spectacular ularni o'tkazib yuboradi.)
"""
from django.urls import include, path

urlpatterns = [
    path('api/partner/', include('apps.partner.urls')),
]

from django.core.cache import cache
from django.db.models import F
from rest_framework import viewsets, filters
from rest_framework.response import Response

from .models import CentralAsiaPost
from .serializers import (
    CentralAsiaPostListSerializer,
    CentralAsiaPostDetailSerializer,
)


class CentralAsiaPostViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/central-asia/                         — pagination + search
    GET /api/central-asia/<slug>/                  — detail (bizning view'ni oshiradi)
    """
    queryset         = CentralAsiaPost.objects.filter(is_published=True)
    filter_backends  = [filters.SearchFilter, filters.OrderingFilter]
    search_fields    = ['title', 'excerpt', 'author_line', 'content']
    ordering_fields  = ['sort_order', 'created_at', 'published_at', 'views_scraped', 'quote_number']
    # sort_order — manba saytdagi tartib (0 = eng yangi, 1-sahifada birinchi)
    ordering         = ['sort_order', '-created_at']
    lookup_field     = 'slug'

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CentralAsiaPostDetailSerializer
        return CentralAsiaPostListSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._unique_view(request, instance)
        # `total_views` UI tomonda `views_scraped + views_local` bilan hisoblanadi,
        # shu sabab yangi qiymatni qaytarish uchun instansiyani qayta yuklaymiz.
        instance.refresh_from_db(fields=['views_local'])
        return Response(
            self.get_serializer(instance, context={'request': request}).data
        )

    @staticmethod
    def _unique_view(request, post: CentralAsiaPost):
        """Bir IP + post kombinatsiyasi uchun 24 soatda 1 marta hisoblanadi."""
        xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
        ip  = (xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')) or 'unknown'
        key = f'ca:view:{post.pk}:{ip}'
        if cache.add(key, 1, timeout=86400):
            CentralAsiaPost.objects.filter(pk=post.pk).update(
                views_local=F('views_local') + 1,
            )

import re
from collections import Counter

from django.core.cache import cache
from django.db.models import F
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CentralAsiaPost
from utils.request_ip import client_ip
from .serializers import (
    CentralAsiaPostListSerializer,
    CentralAsiaPostDetailSerializer,
)
from utils.cache import CachedListMixin, NS_CENTRAL_ASIA, cached_action


class CentralAsiaPostViewSet(CachedListMixin, viewsets.ReadOnlyModelViewSet):
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
    cache_namespace  = NS_CENTRAL_ASIA

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

    @action(detail=False, url_path='stats')
    @cached_action(namespace=NS_CENTRAL_ASIA, ttl=300)
    def stats(self, request):
        """
        GET /api/central-asia/stats/
        To'plam sahifasi tepasidagi raqamlar va yon paneldagi mavzular:
          { articles, authors, topics: [{name, count}], languages: [..] }
        """
        posts = list(self.get_queryset().only('title', 'author_line', 'source_category'))

        authors: set[str] = set()
        for p in posts:
            for name in re.split(r'[,;]', p.author_line or ''):
                name = name.strip()
                if name:
                    authors.add(name.lower())

        topics = Counter((p.source_category or 'Central Asia').strip() for p in posts)

        langs: list[str] = []
        for p in posts:
            t = p.title
            if re.search(r'[ўқғҳЎҚҒҲ]', t):
                code = 'ЎЗ'
            elif re.search(r'[а-яА-ЯёЁ]', t):
                code = 'RU'
            elif re.search(r'(the|and|of|in|for|with|study|library|libraries)', t, re.I):
                code = 'EN'
            else:
                code = 'UZ'
            if code not in langs:
                langs.append(code)

        return Response({
            'articles':  len(posts),
            'authors':   len(authors),
            'topics':    [{'name': k, 'count': v} for k, v in topics.most_common(8)],
            'languages': langs,
        })

    @staticmethod
    def _unique_view(request, post: CentralAsiaPost):
        """Bir IP + post kombinatsiyasi uchun 24 soatda 1 marta hisoblanadi."""
        ip = client_ip(request)
        key = f'ca:view:{post.pk}:{ip}'
        if cache.add(key, 1, timeout=86400):
            CentralAsiaPost.objects.filter(pk=post.pk).update(
                views_local=F('views_local') + 1,
            )

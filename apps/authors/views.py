from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings

from .models import Author
from .serializers import AuthorListSerializer, AuthorDetailSerializer
from utils.request_ip import client_ip
from utils.cache import CachedListMixin, NS_AUTHORS


class AuthorViewSet(CachedListMixin, viewsets.ReadOnlyModelViewSet):
    """
    Profil egalari — kamida bitta maqolasi jurnalda chop etilgan mualliflar
    (Telegram bot, qo'lda yoki PDF parser orqali). AI ajratgan ismlar profil olmaydi.
    """
    queryset = (
        Author.objects
        .filter(articles__issue__isnull=False)
        .prefetch_related('articles')
        .distinct()
    )
    filter_backends  = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields    = ['name', 'org', 'role']
    ordering_fields  = ['name']
    ordering         = ['name']
    lookup_field     = 'slug'
    cache_namespace  = NS_AUTHORS

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return AuthorDetailSerializer
        return AuthorListSerializer

    def get_object(self):
        """
        Slug bo'yicha topadi. Topilmasa — eski (birlashtirilgan) manzillar
        orasidan qidiradi, shunda eski havolalar 404 bermaydi.
        """
        from django.http import Http404
        from .models import AuthorAlias

        try:
            return super().get_object()
        except Http404:
            slug = self.kwargs.get(self.lookup_field)
            alias = (
                AuthorAlias.objects
                .select_related('author')
                .filter(slug=slug)
                .first()
            )
            if alias is None:
                raise
            return alias.author

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._unique_view(request, instance)
        serializer = self.get_serializer(instance, context={'request': request})
        return Response(serializer.data)

    @staticmethod
    def _unique_view(request, author):
        """Bir IP+author 24 soatda 1 marta hisoblanadi."""
        from django.core.cache import cache
        ip = client_ip(request)
        key = f'aview:{author.pk}:{ip}'
        if cache.add(key, 1, timeout=86400):
            author.increment_profile_views()

    # ── Bot endpoints ─────────────────────────────────────────────────────────

    @action(detail=False, methods=['get'], url_path='by-telegram',
            permission_classes=[AllowAny])
    def by_telegram(self, request):
        """GET /api/authors/by-telegram/?chat_id=…&secret=…"""
        if request.query_params.get('secret') != settings.BOT_SECRET:
            return Response({'error': 'Forbidden'}, status=403)
        chat_id = request.query_params.get('chat_id', '')
        if not chat_id:
            return Response({'error': 'chat_id talab etiladi'}, status=400)
        try:
            author = Author.objects.get(telegram_chat_id=int(chat_id))
        except (Author.DoesNotExist, ValueError):
            return Response({'error': 'Muallif topilmadi'}, status=404)
        return Response(AuthorDetailSerializer(author, context={'request': request}).data)

    @action(detail=False, methods=['patch'], url_path='update-profile',
            parser_classes=[MultiPartParser, FormParser, JSONParser],
            permission_classes=[AllowAny])
    def update_profile(self, request):
        """PATCH /api/authors/update-profile/?chat_id=…&secret=…"""
        secret  = request.data.get('secret') or request.query_params.get('secret', '')
        chat_id = request.data.get('chat_id') or request.query_params.get('chat_id', '')

        if secret != settings.BOT_SECRET:
            return Response({'error': 'Forbidden'}, status=403)
        if not chat_id:
            return Response({'error': 'chat_id talab etiladi'}, status=400)

        try:
            author = Author.objects.get(telegram_chat_id=int(chat_id))
        except (Author.DoesNotExist, ValueError):
            return Response({'error': 'Muallif topilmadi'}, status=404)

        # Ruxsat berilgan matn maydonlari
        for field in ('name', 'bio', 'org', 'degree'):
            if field in request.data:
                setattr(author, field, request.data[field])

        # Rasm
        if 'avatar' in request.FILES:
            author.avatar = request.FILES['avatar']

        author.save()
        return Response(
            AuthorDetailSerializer(author, context={'request': request}).data
        )

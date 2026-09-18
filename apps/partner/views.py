"""
Hamkor (tashqi xizmat) API'si — /api/partner/

  POST /api/partner/auth/token/            client_id + client_secret → access + refresh
  POST /api/partner/auth/refresh/          refresh → yangi access + refresh
  GET  /api/partner/articles/                  chop etilgan maqolalar ro'yxati (yangidan eskiga)
  GET  /api/partner/articles/<id>/             bitta maqola: sarlavha + file_url (to'liq manzil)
  GET  /api/partner/articles/<id>/file/<nom>   maqolaning haqiqiy fayli (PDF/DOCX)
  GET  /api/partner/docs/                      hamkor hujjat sahifasi (client_id/secret bilan kiriladi)

Beriladigan ma'lumot ATAYLAB cheklangan: id, sarlavha, sana va fayl.
Abstrakt, tarkib, mualliflar, kalit so'zlar va statistika chiqmaydi.
"""
import logging
import mimetypes
import os

from django.db.models import DateField, F
from django.db.models.functions import Cast, Coalesce
from django.http import FileResponse, Http404

from drf_spectacular.utils import (
    OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema,
)
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from apps.articles.models import Article

from .authentication import PartnerIdentity, PartnerJWTAuthentication
from .models import PartnerClient
from .serializers import (
    PartnerArticleDetailSerializer,
    PartnerArticleListSerializer,
    TokenPairSerializer,
    TokenRefreshRequestSerializer,
    TokenRequestSerializer,
)
from .tokens import PartnerRefreshToken, issue_pair

logger = logging.getLogger(__name__)


# ── Ruxsat va pagination ─────────────────────────────────────────────────────

class IsPartner(BasePermission):
    message = 'Bu endpoint faqat hamkor tokeni bilan ishlaydi.'

    def has_permission(self, request, view):
        return isinstance(request.user, PartnerIdentity)


class PartnerPagination(PageNumberPagination):
    """50 tadan, faqat `?page=N` — boshqa parametr yo'q (hamkor uchun sodda)."""
    page_size = 50

    def get_paginated_response(self, data):
        return Response({
            'count':    self.page.paginator.count,
            'next':     self.get_next_link(),
            'previous': self.get_previous_link(),
            'results':  data,
        })


# ── Umumiy queryset ──────────────────────────────────────────────────────────

def published_articles():
    """
    Chop etilgan (jurnal soniga kiritilgan) va haqiqiy fayli bor maqolalar,
    eng yangisidan eskisiga.

    Tartib: nashr sanasi (bo'lmasa — yaratilgan sana) bo'yicha kamayish tartibida.
    """
    return (
        Article.objects
        .filter(issue__isnull=False)
        .exclude(source_file='')
        .exclude(source_file__isnull=True)
        .annotate(sort_date=Coalesce('published_at', Cast('created_at', DateField())))
        .order_by(F('sort_date').desc(nulls_last=True), '-created_at')
        .only('slug', 'title', 'published_at', 'created_at', 'source_file')
    )


# ── Autentifikatsiya ─────────────────────────────────────────────────────────

@extend_schema(
    tags=['Partner API'],
    summary='Token olish',
    description=(
        'client_id va client_secret ni access + refresh tokenga almashtiradi.\n\n'
        'Keyingi so\'rovlarda: `Authorization: Bearer <access>`'
    ),
    request=TokenRequestSerializer,
    responses={
        200: TokenPairSerializer,
        401: OpenApiResponse(description='client_id yoki client_secret noto\'g\'ri'),
        429: OpenApiResponse(description='So\'rovlar chegarasi oshdi'),
    },
    examples=[OpenApiExample(
        'So\'rov',
        value={'client_id': 'kb_1a2b3c…', 'client_secret': '…'},
        request_only=True,
    )],
)
class PartnerTokenView(APIView):
    authentication_classes = []
    permission_classes     = [AllowAny]
    throttle_scope         = 'partner_token'

    def post(self, request):
        serializer = TokenRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            client = PartnerClient.objects.get(
                client_id=data['client_id'], is_active=True,
            )
        except PartnerClient.DoesNotExist:
            logger.info('Partner token: mijoz topilmadi (%s)', data['client_id'])
            return Response(
                {'error': 'invalid_client', 'detail': 'client_id yoki client_secret noto\'g\'ri'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not client.check_secret(data['client_secret']):
            logger.info('Partner token: secret mos kelmadi (%s)', client.client_id)
            return Response(
                {'error': 'invalid_client', 'detail': 'client_id yoki client_secret noto\'g\'ri'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        client.touch()
        return Response(issue_pair(client))


@extend_schema(
    tags=['Partner API'],
    summary='Tokenni yangilash',
    description='Refresh token yordamida yangi access + refresh juftligi olinadi.',
    request=TokenRefreshRequestSerializer,
    responses={
        200: TokenPairSerializer,
        401: OpenApiResponse(description='Refresh token yaroqsiz yoki muddati tugagan'),
    },
)
class PartnerTokenRefreshView(APIView):
    authentication_classes = []
    permission_classes     = [AllowAny]
    throttle_scope         = 'partner_token'

    def post(self, request):
        serializer = TokenRefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refresh = PartnerRefreshToken(serializer.validated_data['refresh'])
        except TokenError:
            return Response(
                {'error': 'invalid_grant', 'detail': 'Refresh token yaroqsiz yoki muddati tugagan'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            client = PartnerClient.objects.get(pk=refresh.get('client_id'), is_active=True)
        except (PartnerClient.DoesNotExist, ValueError, TypeError):
            return Response(
                {'error': 'invalid_client', 'detail': 'Mijoz topilmadi yoki o\'chirilgan'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Tokenlar bekor qilingan bo'lsa refresh ham ishlamaydi
        if int(refresh.get('tv') or 1) != int(client.token_version or 1):
            return Response(
                {'error': 'invalid_grant', 'detail': 'Token bekor qilingan'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(issue_pair(client))


# ── Maqolalar ────────────────────────────────────────────────────────────────

@extend_schema(
    tags=['Partner API'],
    summary='Maqolalar ro\'yxati',
    description=(
        'Chop etilgan va fayli mavjud maqolalar — eng yangisidan eskisiga, 50 tadan.\n\n'
        'Har bir element: `id`, `title`, `published_at`. Boshqa ma\'lumot berilmaydi.\n'
        'Faylni olish uchun `id` bo\'yicha detal endpointiga murojaat qiling.'
    ),
    parameters=[OpenApiParameter('page', int, description='Sahifa raqami')],
    responses={200: PartnerArticleListSerializer(many=True)},
)
class PartnerArticleListView(ListAPIView):
    authentication_classes = [PartnerJWTAuthentication]
    permission_classes     = [IsPartner]
    throttle_scope         = 'partner'
    serializer_class       = PartnerArticleListSerializer
    pagination_class       = PartnerPagination
    filter_backends        = []          # global search/ordering parametrlari bu yerda yo'q

    def get_queryset(self):
        return published_articles()


@extend_schema(
    tags=['Partner API'],
    summary='Bitta maqola',
    description=(
        'Maqolaning sarlavhasi va fayli. `file_url` — faylning to\'liq tayyor '
        'manzili, o\'sha token bilan to\'g\'ridan-to\'g\'ri yuklab olinadi.'
    ),
    responses={
        200: PartnerArticleDetailSerializer,
        404: OpenApiResponse(description='Maqola topilmadi yoki fayli yo\'q'),
    },
)
class PartnerArticleDetailView(RetrieveAPIView):
    authentication_classes = [PartnerJWTAuthentication]
    permission_classes     = [IsPartner]
    throttle_scope         = 'partner'
    serializer_class       = PartnerArticleDetailSerializer
    lookup_field           = 'pk'
    lookup_url_kwarg       = 'id'

    def get_queryset(self):
        return published_articles()


@extend_schema(
    tags=['Partner API'],
    summary='Maqola faylini yuklab olish',
    description='Maqolaning haqiqiy fayli (PDF yoki DOCX) — binar oqim sifatida.',
    responses={
        (200, 'application/octet-stream'): OpenApiResponse(description='Fayl'),
        404: OpenApiResponse(description='Maqola topilmadi yoki fayli yo\'q'),
    },
)
class PartnerArticleFileView(APIView):
    authentication_classes = [PartnerJWTAuthentication]
    permission_classes     = [IsPartner]
    throttle_scope         = 'partner'

    def get(self, request, id, filename=None):
        # `filename` — faqat manzil to'liq va tushunarli bo'lishi uchun
        # (detal javobidagi file_url shu ko'rinishda); tekshirilmaydi.
        article = published_articles().filter(pk=id).first()
        if article is None or not article.source_file:
            raise Http404('Maqola topilmadi yoki fayli yo\'q')

        name = os.path.basename(article.source_file.name)
        content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'

        try:
            handle = article.source_file.open('rb')
        except (OSError, ValueError):
            logger.warning('Partner API: fayl ochilmadi (%s)', article.slug)
            raise Http404('Fayl mavjud emas')

        response = FileResponse(handle, as_attachment=True, filename=name)
        response['Content-Type'] = content_type
        # Fayllar o'zgarmaydi — hamkor CDN'i keshlashi mumkin
        response['Cache-Control'] = 'private, max-age=86400'
        return response

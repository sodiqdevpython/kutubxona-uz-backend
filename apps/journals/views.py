from rest_framework import viewsets, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Journal, Issue
from .serializers import JournalSerializer, IssueSerializer


class JournalViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset         = Journal.objects.prefetch_related('issues')
    serializer_class = JournalSerializer
    pagination_class = None


class IssueViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Issue.objects.select_related('journal').prefetch_related('articles')
    serializer_class = IssueSerializer
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['year', 'season', 'is_current', 'is_upcoming']
    pagination_class = None

    @action(detail=False, url_path='archive')
    def archive(self, request):
        """
        GET /api/issues/archive/
        Returns issues grouped by year:
        [ { year: 2026, issues: [...] }, ... ]
        """
        qs = self.get_queryset().order_by('-year', '-number')
        years: dict = {}
        for issue in qs:
            years.setdefault(issue.year, []).append(issue)

        data = [
            {
                'year':   year,
                'issues': IssueSerializer(issues, many=True, context={'request': request}).data,
            }
            for year, issues in sorted(years.items(), reverse=True)
        ]
        return Response(data)

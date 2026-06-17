from rest_framework import mixins, viewsets, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Comment
from .serializers import CommentSerializer, CommentCreateSerializer


class CommentViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset         = Comment.objects.filter(is_approved=True, parent=None)
    filter_backends  = [DjangoFilterBackend]
    filterset_fields = ['article', 'issue']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CommentCreateSerializer
        return CommentSerializer

    def get_queryset(self):
        # DELETE va child-comment'lar uchun parent=None filter shart emas
        if self.action == 'destroy':
            return Comment.objects.all()
        return super().get_queryset()

    def create(self, request, *args, **kwargs):
        serializer = CommentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(is_approved=True)
        out = CommentSerializer(comment)
        return Response(out.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        # Faqat admin (is_staff) o'chira oladi
        if not request.user.is_authenticated or not request.user.is_staff:
            raise PermissionDenied("Faqat adminlar izohni o'chira oladi.")
        return super().destroy(request, *args, **kwargs)

from rest_framework import serializers
from .models import Comment


class CommentSerializer(serializers.ModelSerializer):
    replies = serializers.SerializerMethodField()

    class Meta:
        model  = Comment
        fields = (
            'id', 'name', 'text', 'parent',
            'created_at', 'replies',
        )
        read_only_fields = ('id', 'created_at', 'replies')

    def get_replies(self, obj):
        qs = obj.replies.filter(is_approved=True)
        return CommentSerializer(qs, many=True).data


class CommentCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Comment
        fields = ('article', 'parent', 'name', 'text')

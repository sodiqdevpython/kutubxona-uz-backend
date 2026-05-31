from rest_framework import serializers
from .models import Chat, Message


class MessageSerializer(serializers.ModelSerializer):
    image_url    = serializers.SerializerMethodField()
    document_url = serializers.SerializerMethodField()
    document_name = serializers.SerializerMethodField()

    def _abs(self, f):
        if not f: return None
        request = self.context.get('request')
        return request.build_absolute_uri(f.url) if request else f.url

    def get_image_url(self, obj):    return self._abs(obj.image)
    def get_document_url(self, obj): return self._abs(obj.document)
    def get_document_name(self, obj):
        if not obj.document: return None
        return obj.document.name.split('/')[-1]

    class Meta:
        model  = Message
        fields = (
            'id', 'sender', 'kind',
            'text', 'image_url', 'document_url', 'document_name',
            'is_read', 'created_at',
        )


class ChatListSerializer(serializers.ModelSerializer):
    """Chat ro'yxati uchun — sidebar'da chiqadigan qisqa ko'rinish."""
    author_id        = serializers.UUIDField(source='author.id', read_only=True)
    author_name      = serializers.CharField(source='author.name',     read_only=True)
    author_initials  = serializers.CharField(source='author.initials', read_only=True)
    author_avatar_idx = serializers.IntegerField(source='author.avatar_idx', read_only=True)
    author_slug      = serializers.SlugField(source='author.slug', read_only=True)
    telegram_username = serializers.CharField(source='author.telegram_username', read_only=True)

    last_message     = serializers.SerializerMethodField()

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        if not last: return None
        return {
            'text':       last.text,
            'kind':       last.kind,
            'sender':     last.sender,
            'created_at': last.created_at.isoformat(),
        }

    class Meta:
        model  = Chat
        fields = (
            'id', 'author_id', 'author_name', 'author_initials',
            'author_avatar_idx', 'author_slug', 'telegram_username',
            'is_blocked', 'unread_count', 'last_message_at', 'last_message',
            'created_at',
        )

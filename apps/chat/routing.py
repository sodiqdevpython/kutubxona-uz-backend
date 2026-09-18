from django.urls import path

from .consumers import AdminChatConsumer

websocket_urlpatterns = [
    path('ws/admin/chat/', AdminChatConsumer.as_asgi()),
]

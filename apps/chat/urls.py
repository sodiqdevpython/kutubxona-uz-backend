from django.urls import path
from . import views

# Admin URL'lari panel app urls.py orqali include qilinmaydi — alohida prefix bilan
admin_patterns = [
    path('admin/chat/',                     views.AdminChatListView.as_view(),     name='admin-chat-list'),
    path('admin/chat/by-author/<slug:slug>/', views.AdminChatByAuthorView.as_view(), name='admin-chat-by-author'),
    path('admin/chat/<uuid:chat_id>/messages/', views.AdminChatMessagesView.as_view(), name='admin-chat-messages'),
    path('admin/chat/<uuid:chat_id>/send/',     views.AdminChatSendView.as_view(),     name='admin-chat-send'),
    path('admin/chat/<uuid:chat_id>/block/',    views.AdminChatBlockView.as_view(),    name='admin-chat-block'),
    path('admin/chat/<uuid:chat_id>/read/',     views.AdminChatReadView.as_view(),     name='admin-chat-read'),
    path('admin/chat/<uuid:chat_id>/',          views.AdminChatDeleteView.as_view(),   name='admin-chat-delete'),
]

bot_patterns = [
    path('chat/bot-message/', views.BotMessageView.as_view(), name='bot-message'),
]

urlpatterns = admin_patterns + bot_patterns

from django.db import models


def unread_message_count(request):
    """Add unread message count to template context for navbar badge."""
    if not hasattr(request, 'user') or not request.user.is_authenticated:
        return {}

    from .models import Message

    if request.user.is_instructor:
        count = Message.objects.filter(message_type='DM', is_read=False).count()
    elif request.user.is_student or request.user.is_ta:
        count = Message.objects.filter(
            models.Q(recipient=request.user, message_type='REPLY', is_read=False) |
            models.Q(message_type='ANNOUNCEMENT', is_read=False)
        ).count()
    else:
        count = 0

    return {'unread_msg_count': count}

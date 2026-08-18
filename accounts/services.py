from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .utils import email_token_generator


def send_confirmation_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_token_generator.make_token(user)
    link = (
        f"{settings.FRONTEND_CONFIRM_URL}"
        f"?uid={uid}&token={token}"
    )
    send_mail(
        subject='Verify email: Online Shop',
        message=f'Hello {user.first_name}!\n\nVerify email:\n{link}\n',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )
    return uid, token  # token возвращаем только для тестов/шелла, в проде не логировать
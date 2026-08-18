from django.contrib.auth import get_user_model
from django.utils.encoding import force_str
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.tokens import PasswordResetTokenGenerator



User = get_user_model()





class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user: User, timestamp):
        return (
            str(user.pk) +
            str(timestamp) +
            str(user.is_active) +
            str(user.email)
        )

email_token_generator = EmailVerificationTokenGenerator()


def confirm_user_email(uid: str, token: str) -> tuple[bool, str]:

    user_id = force_str(urlsafe_base64_decode(uid))
    user = User.objects.get(pk=user_id)
    if not email_token_generator.check_token(user, token):
        return False, "Токен недействителен"

    user.email_confirmed = True
    user.save(update_fields=["email_confirmed"])

    return True, "Email подтверждён"
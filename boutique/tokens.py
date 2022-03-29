from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils import six

class InviteTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, invite, timestamp):
        return (
            six.text_type(invite.pk) + six.text_type(timestamp) +
            six.text_type(invite.profile.email_confirmed)
        )

invite_token = InviteTokenGenerator()
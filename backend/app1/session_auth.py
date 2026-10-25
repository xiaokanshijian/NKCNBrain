"""Bridge the existing NKCN account model to a server-side Django session."""
from django.middleware.csrf import rotate_token
from django.utils.crypto import constant_time_compare, salted_hmac

USER_ID_KEY = "nkcn_authenticated_user_id"
AUTH_HASH_KEY = "nkcn_authenticated_user_hash"

def _auth_hash(user):
    # Bind a session to the account and its current password without storing either password.
    return salted_hmac(
        "nkcn.public.account-session",
        f"{user.pk}:{user.username}:{user.password}",
        algorithm="sha256",
    ).hexdigest()

def clear_user_session(request):
    request.session.flush()

def establish_user_session(request, user):
    request.session.cycle_key()
    request.session[USER_ID_KEY] = user.pk
    request.session[AUTH_HASH_KEY] = _auth_hash(user)
    rotate_token(request)

def get_session_user(request):
    session = getattr(request, "session", None)
    if session is None:
        return None
    user_id = session.get(USER_ID_KEY)
    if user_id is None:
        return None
    # Import lazily so unrelated commands need not initialize the user models.
    from app1.models import User
    try:
        user = User.objects.get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        clear_user_session(request)
        return None
    recorded_hash = session.get(AUTH_HASH_KEY)
    if (user.allowed != 1 or not isinstance(recorded_hash, str)
            or not constant_time_compare(recorded_hash, _auth_hash(user))):
        clear_user_session(request)
        return None
    return user

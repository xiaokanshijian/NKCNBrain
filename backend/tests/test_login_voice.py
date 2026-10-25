"""Actual HTTP views + CSRF/session middleware + isolated SQLite account tables."""
import json
import os
from datetime import timedelta
from unittest.mock import patch
from django.conf import settings
from django.contrib.sessions.models import Session
from django.db import DatabaseError
from django.test import Client, TestCase
from django.utils import timezone
from app1.models import User, UserSceneParams
from app1.session_auth import USER_ID_KEY, AUTH_HASH_KEY
from zym.models import scene

ORIGIN = "http://localhost:8080"

class LoginVoiceIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.user = User.objects.create(username="voice-user", password="unit-password", allowed=1)
        self.other = User.objects.create(username="other-user", password="other-password", allowed=1)
        scene.objects.create(username="unit-scene", sceneDescription="unit description")
        self.env = patch.dict(os.environ, {
            "XFYUN_APP_ID": "unit-app", "XFYUN_API_KEY": "unit-key", "XFYUN_API_SECRET": "unit-secret"
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def csrf(self, client=None):
        client = client or self.client
        response = client.get("/api/auth/csrf", HTTP_ORIGIN=ORIGIN)
        self.assertEqual(response.status_code, 200)
        return response.json()["csrfToken"]

    def post(self, path, data, client=None):
        client = client or self.client
        return client.post(path, data=json.dumps(data), content_type="application/json",
                           HTTP_ORIGIN=ORIGIN, HTTP_X_CSRFTOKEN=self.csrf(client))

    def login(self, client=None, username="voice-user", password="unit-password", path="/api/verify_user"):
        return self.post(path, {"username": username, "password": password, "choose": "simple"}, client)

    def voice(self, client=None, service="iat"):
        return (client or self.client).get("/api/voice/session", {"service": service}, HTTP_ORIGIN=ORIGIN)

    def test_normal_login_allows_asr_and_tts_and_preserves_response(self):
        self.assertEqual(self.voice().status_code, 401)
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"error_num": 0, "msg": "success", "name": self.user.username,
                                          "coacherName": self.user.coacher, "level": self.user.level})
        self.user.refresh_from_db()
        self.assertEqual(self.user.choose, 1)
        self.assertTrue(UserSceneParams.objects.filter(username=self.user.username).exists())
        for service in ("iat", "tts"):
            result = self.voice(service=service)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["app_id"], "unit-app")
            self.assertNotIn("unit-secret", result.content.decode())
        session = self.client.get("/api/auth/session").json()
        self.assertEqual((session["name"], session["choose"]), (self.user.username, 1))

    def test_trailing_slash_login_is_also_supported_without_redirect(self):
        self.assertEqual(self.login(path="/api/verify_user/").status_code, 200)
        self.assertEqual(self.voice().status_code, 200)

    def test_login_csrf_and_post_required(self):
        self.assertEqual(self.client.get("/api/verify_user", {"username": self.user.username}).status_code, 405)
        response = self.client.post("/api/verify_user", {"username": self.user.username, "password": "unit-password"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.voice().status_code, 401)

    def test_untrusted_origin_cannot_log_in(self):
        token = self.csrf()
        response = self.client.post("/api/verify_user", json.dumps({"username": self.user.username, "password": "unit-password"}),
                                    content_type="application/json", HTTP_X_CSRFTOKEN=token,
                                    HTTP_ORIGIN="https://attacker.example")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.voice().status_code, 401)

    def test_failed_login_clears_previous_session(self):
        self.login()
        response = self.login(password="wrong-password")
        self.assertEqual(response.json()["name"], "0")
        self.assertEqual(self.voice().status_code, 401)
        self.assertEqual(self.client.get("/api/auth/session").status_code, 401)

    def test_unknown_and_unapproved_users_do_not_get_sessions(self):
        for username, allowed in [("missing-user", None), (self.user.username, 0)]:
            if allowed is not None:
                User.objects.filter(pk=self.user.pk).update(allowed=allowed)
            response = self.login(username=username)
            self.assertEqual(response.json()["name"], "0")
            self.assertEqual(self.voice().status_code, 401)

    def test_login_rotates_session_and_does_not_store_password(self):
        old = self.client.session
        old["prelogin"] = "unit-marker"
        old.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = old.session_key
        self.login()
        new_key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertNotEqual(new_key, old.session_key)
        self.assertFalse(Session.objects.filter(session_key=old.session_key).exists())
        stored = Session.objects.get(session_key=new_key).get_decoded()
        self.assertEqual(stored[USER_ID_KEY], self.user.pk)
        self.assertNotIn("unit-password", json.dumps(stored))
        stolen_old_cookie = Client(enforce_csrf_checks=True)
        stolen_old_cookie.cookies[settings.SESSION_COOKIE_NAME] = old.session_key
        self.assertEqual(self.voice(stolen_old_cookie).status_code, 401)

    def test_username_without_verified_session_cannot_obtain_signature(self):
        self.assertEqual(self.client.get("/api/voice/session", {"service": "iat", "username": self.user.username}).status_code, 401)
        session = self.client.session
        session[USER_ID_KEY] = self.user.pk
        session[AUTH_HASH_KEY] = "fabricated"
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key
        self.assertEqual(self.voice().status_code, 401)

    def test_logout_revokes_cookie_and_is_idempotent(self):
        self.login()
        key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        self.assertEqual(self.post("/api/auth/logout", {}).json()["error_num"], 0)
        self.assertEqual(self.voice().status_code, 401)
        self.assertEqual(self.post("/api/auth/logout", {}).status_code, 200)
        replay = Client()
        replay.cookies[settings.SESSION_COOKIE_NAME] = key
        self.assertEqual(self.voice(replay).status_code, 401)

    def test_logout_requires_csrf(self):
        self.login()
        self.assertEqual(self.client.post("/api/auth/logout", {}).status_code, 403)
        self.assertEqual(self.voice().status_code, 200)

    def test_logout_does_not_log_out_another_browser(self):
        another = Client(enforce_csrf_checks=True)
        self.login()
        self.login(another, username=self.other.username, password="other-password")
        self.post("/api/auth/logout", {"username": self.other.username})
        self.assertEqual(self.voice().status_code, 401)
        self.assertEqual(self.voice(another).status_code, 200)

    def test_leaving_notebook_does_not_revoke_login(self):
        self.login()
        response = self.client.post("/api/user_exit/", json.dumps({"username": self.user.username}),
                                    content_type="application/json")
        self.assertEqual(response.json()["error_num"], 0)
        self.assertEqual(self.voice().status_code, 200)

    def test_disabled_user_is_denied_on_next_voice_request(self):
        self.login()
        User.objects.filter(pk=self.user.pk).update(allowed=0)
        self.assertEqual(self.voice().status_code, 401)

    def test_deleted_user_is_denied(self):
        self.login()
        self.user.delete()
        self.assertEqual(self.voice().status_code, 401)

    def test_password_change_revokes_session(self):
        self.login()
        User.objects.filter(pk=self.user.pk).update(password="changed-password")
        self.assertEqual(self.voice().status_code, 401)

    def test_expired_session_is_denied(self):
        self.login()
        key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        Session.objects.filter(session_key=key).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.voice().status_code, 401)

    def test_database_failure_returns_503_without_revoking_session(self):
        self.login()
        key = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        with patch("app1.models.User.objects.get", side_effect=DatabaseError("unit-database-unavailable")):
            self.assertEqual(self.voice().status_code, 503)
            self.assertEqual(self.client.get("/api/auth/session").status_code, 503)
        self.assertEqual(self.client.cookies[settings.SESSION_COOKIE_NAME].value, key)
        self.assertEqual(self.voice().status_code, 200)

    def test_credentials_not_configured_after_login_returns_503(self):
        self.login()
        with patch.dict(os.environ, {"XFYUN_API_SECRET": ""}):
            response = self.voice()
        self.assertEqual(response.status_code, 503)

    def test_cookie_and_cors_headers_allow_credentialed_browser_requests(self):
        response = self.login()
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(response["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(response["Access-Control-Allow-Credentials"], "true")
        preflight = self.client.options("/api/verify_user", HTTP_ORIGIN=ORIGIN,
                     HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
                     HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken")
        self.assertEqual(preflight["Access-Control-Allow-Credentials"], "true")
        self.assertIn("x-csrftoken", preflight["Access-Control-Allow-Headers"])

"""Authentication for Spotify.

Spotify dropped raw username/password login for newly-created accounts in
2024 and is sunset-ing it for existing accounts. The reliable path in 2026
is OAuth — specifically the Authorization Code flow with PKCE so we don't
need to embed (and rotate) a client secret in a desktop app.

To stay GUI-only (no config-file digging), tide opens the user's default
browser to Spotify's authorize URL and listens on a 127.0.0.1 loopback for
the callback. Same pattern as the YouTube Music cookie-import sign-in:
the modal walks the user step-by-step, the network plumbing is invisible.

The granted refresh token is persisted, AES-encrypted, at
``~/.config/tide/spotify.json`` and reused on next launch. We refresh the
access token transparently before any Web API call that's about to expire.

For playback, librespot consumes the same refresh token via its
``--access-token`` arg; we hand it a fresh one every time the subprocess
starts. The Web API and librespot share the user's auth so there's a
single sign-in and a single source of truth.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import json
import os
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from . import config


# ---------- client id ----------
#
# PKCE doesn't require a client secret, but it still needs a client_id
# registered at developer.spotify.com. This is tide-the-project's
# registered app id — public on purpose (PKCE flow means the client_id
# alone can't be misused). Power users who'd rather not share rate
# limits can paste their own dev-app client_id in Settings → Sources
# → Spotify → [⚙]; the per-source override takes precedence.
TIDE_DEFAULT_CLIENT_ID = "16c9d40674b245f08db93f07dca0c6c0"

# Scopes we ask for. Keep the list tight to what tide actually uses so the
# consent screen looks honest. `streaming` is the one librespot needs to
# play tracks; the rest power search/library/playlists/like.
DEFAULT_SCOPES = (
    "user-read-private "
    "user-read-email "
    "user-library-read "
    "user-library-modify "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-read-playback-state "
    "user-modify-playback-state "
    "streaming"
)

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT_DEFAULT = 8898
CALLBACK_PATH = "/callback"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


# ---------- saved-token model ----------


@dataclass
class SpotifyTokens:
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0.0           # unix seconds
    scopes: str = ""
    client_id: str = ""

    def is_expired(self, slack_seconds: float = 30.0) -> bool:
        return time.time() + slack_seconds >= self.expires_at


# ---------- encryption helpers ----------
#
# We already depend on `cryptography` for the YT browser-cookie pipeline,
# so re-use it here. The Fernet key is derived from a per-user passphrase
# stitched together from the machine-id + home path. This isn't kwallet-
# grade — anyone with read access to the user's home can derive the key —
# but it does mean the token file isn't readable as plain text by random
# log scrapers, and the file itself is chmod 600.


def _machine_seed() -> bytes:
    bits: list[bytes] = []
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            with open(p, "rb") as f:
                bits.append(f.read().strip())
                break
        except OSError:
            continue
    bits.append(str(Path.home()).encode("utf-8"))
    bits.append(b"tide-spotify-v1")
    return b"|".join(bits)


def _fernet() -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"tide.spotify.kdf.v1",
        iterations=200_000,
    )
    raw = kdf.derive(_machine_seed())
    return Fernet(base64.urlsafe_b64encode(raw))


# ---------- token persistence ----------


def have_auth() -> bool:
    return config.SPOTIFY_AUTH_FILE.is_file()


def save_tokens(tokens: SpotifyTokens) -> Path:
    payload = json.dumps({
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "expires_at": tokens.expires_at,
        "scopes": tokens.scopes,
        "client_id": tokens.client_id,
    }).encode("utf-8")
    enc = _fernet().encrypt(payload)
    config.SPOTIFY_AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.SPOTIFY_AUTH_FILE.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(enc)
    tmp.replace(config.SPOTIFY_AUTH_FILE)
    try:
        config.SPOTIFY_AUTH_FILE.chmod(0o600)
    except OSError:
        pass
    return config.SPOTIFY_AUTH_FILE


def load_tokens() -> SpotifyTokens | None:
    if not config.SPOTIFY_AUTH_FILE.is_file():
        return None
    try:
        with open(config.SPOTIFY_AUTH_FILE, "rb") as f:
            enc = f.read()
        raw = _fernet().decrypt(enc)
        data = json.loads(raw.decode("utf-8"))
    except (OSError, InvalidToken, ValueError, json.JSONDecodeError):
        return None
    return SpotifyTokens(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        expires_at=float(data.get("expires_at") or 0),
        scopes=data.get("scopes", ""),
        client_id=data.get("client_id", ""),
    )


def clear_saved_auth() -> None:
    config.SPOTIFY_AUTH_FILE.unlink(missing_ok=True)


# ---------- PKCE helpers ----------


def _gen_pkce_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(64)).rstrip(b"=").decode("ascii")


def _pkce_challenge(verifier: str) -> str:
    h = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(h).rstrip(b"=").decode("ascii")


# ---------- loopback callback server ----------


def _free_port() -> int:
    """Pick a port we can bind to. Prefer the canonical 8898 (matches the
    Redirect URI users register in their dev app); fall back to any free
    port if it's busy. The redirect URI sent in the authorize URL has to
    match exactly what the dev app has registered, so falling back means
    the user must have registered multiple redirect URIs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((CALLBACK_HOST, CALLBACK_PORT_DEFAULT))
    except OSError:
        s.close()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((CALLBACK_HOST, 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _CallbackResult:
    def __init__(self) -> None:
        self.code: str | None = None
        self.error: str | None = None
        self.state: str | None = None
        self.event = threading.Event()


def _make_handler(expected_state: str, result: _CallbackResult):
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_a, **_kw) -> None:    # silence access log
            return

        def do_GET(self) -> None:
            url = urllib.parse.urlparse(self.path)
            if url.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return
            qs = urllib.parse.parse_qs(url.query)
            state = qs.get("state", [""])[0]
            if state != expected_state:
                result.error = "state mismatch"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"state mismatch - close this tab and try again")
                result.event.set()
                return
            err = qs.get("error", [""])[0]
            if err:
                result.error = err
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"spotify denied authorization. close this tab and try again.")
                result.event.set()
                return
            code = qs.get("code", [""])[0]
            if not code:
                result.error = "no code"
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"no authorization code - close this tab and try again")
                result.event.set()
                return
            result.code = code
            result.state = state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><html><head><title>tide</title>"
                b"<style>body{background:#0b0b0b;color:#d4b95e;font:14px ui-monospace,monospace;"
                b"display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
                b"main{max-width:480px;text-align:center;line-height:1.6}</style></head>"
                b"<body><main><h1 style='font-weight:600;font-size:18px;letter-spacing:0.1em'>"
                b"tide \xe2\x80\xa2 connected to spotify</h1>"
                b"<p style='opacity:0.7'>you can close this tab and return to tide.</p>"
                b"</main></body></html>"
            )
            result.event.set()
    return Handler


# ---------- OAuth flow ----------


@dataclass
class AuthFlow:
    client_id: str
    scopes: str = DEFAULT_SCOPES
    port: int = 0
    verifier: str = ""
    state: str = ""
    redirect_uri: str = field(default="", init=False)
    _cancelled: bool = field(default=False, init=False, repr=False)
    _pending: _CallbackResult | None = field(default=None, init=False, repr=False)

    def cancel(self) -> None:
        """Unblock a pending ``run_callback()`` promptly. Thread-safe: the
        GUI thread calls this when the sign-in dialog closes; the blocked
        worker-thread call wakes up, shuts the loopback server down, and
        raises RuntimeError instead of sitting out the full timeout."""
        self._cancelled = True
        pending = self._pending
        if pending is not None:
            pending.event.set()

    def authorize_url(self) -> str:
        self.port = self.port or _free_port()
        self.verifier = self.verifier or _gen_pkce_verifier()
        self.state = self.state or secrets.token_urlsafe(16)
        self.redirect_uri = f"http://{CALLBACK_HOST}:{self.port}{CALLBACK_PATH}"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": self.scopes,
            "state": self.state,
            "code_challenge_method": "S256",
            "code_challenge": _pkce_challenge(self.verifier),
            "show_dialog": "false",
        }
        return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)

    def run_callback(self, timeout_seconds: float = 180.0) -> str:
        """Block until the user completes the browser flow. Returns the
        authorization code or raises RuntimeError on timeout, error, or
        ``cancel()``."""
        if not self.port:
            raise RuntimeError("call authorize_url() first")
        result = _CallbackResult()
        self._pending = result
        if self._cancelled:
            # cancel() raced us before the wait started — bail before
            # even binding the server.
            raise RuntimeError("sign-in cancelled")
        server = http.server.HTTPServer(
            (CALLBACK_HOST, self.port),
            _make_handler(self.state, result),
        )
        # Serve until the callback fires, the timeout lapses, or an
        # external caller (the sign-in dialog closing) calls cancel(),
        # which sets the shared event to wake us early.
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        ok = result.event.wait(timeout=timeout_seconds)
        server.shutdown()
        server.server_close()
        t.join(timeout=1.0)
        if self._cancelled:
            raise RuntimeError("sign-in cancelled")
        if not ok:
            raise RuntimeError("timed out waiting for spotify authorization")
        if result.error:
            raise RuntimeError(f"spotify auth failed: {result.error}")
        return result.code or ""

    def exchange_code(self, code: str) -> SpotifyTokens:
        body = urllib.parse.urlencode({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": self.verifier,
        }).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.load(resp)
        return SpotifyTokens(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + float(data.get("expires_in") or 3600),
            scopes=data.get("scope", self.scopes),
            client_id=self.client_id,
        )


# ---------- refresh ----------


def refresh_tokens(tokens: SpotifyTokens) -> SpotifyTokens:
    """Refresh the access token in-place. Spotify rotates the refresh
    token on each call as of 2024 — if the response includes a new
    refresh_token we keep it, otherwise we keep the old one (allowed by
    spec)."""
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": tokens.refresh_token,
        "client_id": tokens.client_id,
    }).encode("utf-8")
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.load(resp)
    return SpotifyTokens(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token") or tokens.refresh_token,
        expires_at=time.time() + float(data.get("expires_in") or 3600),
        scopes=data.get("scope", tokens.scopes),
        client_id=tokens.client_id,
    )


# ---------- module-level token cache ----------
#
# A single in-memory cache so SpotifySource and LibrespotBackend share a
# view of the current tokens. Both call ``current_access_token()`` (which
# refreshes if needed) without having to plumb mutable state through
# every constructor.
#
# All refreshing runs under one lock: Spotify ROTATES the refresh token on
# every use, so two threads refreshing concurrently with the same stored
# token means the loser presents an already-burned token and gets
# ``invalid_grant`` — which can invalidate the whole grant chain and force
# the user back through the browser flow for no reason.

_cached: SpotifyTokens | None = None
_refresh_lock = threading.Lock()
_refresh_dead = False           # invalid_grant seen — re-sign-in required
_refresh_backoff_until = 0.0    # don't re-attempt before this (network woes)

_NETWORK_BACKOFF_SECONDS = 30.0


def _ensure_loaded() -> SpotifyTokens | None:
    global _cached
    if _cached is None:
        _cached = load_tokens()
    return _cached


def saved_tokens() -> SpotifyTokens | None:
    """The stored tokens as-is — possibly expired, but NO network. Boot
    uses this to decide whether to register the Spotify source without
    blocking the GUI thread on a token refresh (and without dropping the
    source entirely when the machine is offline)."""
    return _ensure_loaded()


def current_tokens() -> SpotifyTokens | None:
    t = _ensure_loaded()
    if t is None:
        return None
    if t.is_expired():
        return refresh_and_persist()
    return t


def refresh_and_persist() -> SpotifyTokens | None:
    global _cached, _refresh_dead, _refresh_backoff_until
    with _refresh_lock:
        t = _ensure_loaded()
        if t is None or not t.refresh_token:
            return None
        # Someone else may have refreshed while we waited on the lock; if
        # so their result is fresh and re-refreshing would burn a rotated
        # token. Same lock also serializes the save.
        if not t.is_expired():
            return t
        if _refresh_dead:
            return None            # token is revoked; only sign-in resets
        if time.time() < _refresh_backoff_until:
            return None            # offline recently — don't hammer
        try:
            new = refresh_tokens(t)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if exc.code in (400, 401) and "invalid_grant" in body:
                # Definitive: the refresh token is revoked or expired.
                # Retrying can never succeed — flag it and tell the UI
                # (once) so the user gets the sign-in toast instead of a
                # session that silently 401s forever.
                _refresh_dead = True
                _notify_auth_expired()
            else:
                _refresh_backoff_until = time.time() + _NETWORK_BACKOFF_SECONDS
            return None
        except (urllib.error.URLError, OSError, ValueError):
            # Transient/network — keep the stored token and back off.
            _refresh_backoff_until = time.time() + _NETWORK_BACKOFF_SECONDS
            return None
        save_tokens(new)
        _cached = new
        _refresh_backoff_until = 0.0
        return new


def auth_is_dead() -> bool:
    """True when a refresh came back ``invalid_grant`` — the UI shows
    "session expired" instead of pretending we're signed in."""
    return _refresh_dead


def _notify_auth_expired() -> None:
    # Late import: sources package imports this module.
    try:
        from .sources import registry
        registry().notify_auth_expired("spotify")
    except Exception:
        pass


def current_access_token() -> str:
    t = current_tokens()
    return t.access_token if t else ""


def set_cached(tokens: SpotifyTokens) -> None:
    """Called after a successful sign-in to seed the cache without a
    disk round-trip."""
    global _cached, _refresh_dead, _refresh_backoff_until
    _cached = tokens
    _refresh_dead = False
    _refresh_backoff_until = 0.0


def clear_cached() -> None:
    global _cached, _refresh_dead, _refresh_backoff_until
    _cached = None
    _refresh_dead = False
    _refresh_backoff_until = 0.0
    clear_saved_auth()


# ---------- effective client_id ----------


def effective_client_id(user_override: str = "") -> str:
    """Pick the client_id to use. Order:
      1. Explicit user override (per-source [⚙] field)
      2. TIDE_SPOTIFY_CLIENT_ID env var (CI / dev convenience)
      3. The tide-shipped default (TIDE_DEFAULT_CLIENT_ID)
    Returns empty string if none configured — caller should surface the
    "no client_id set" empty-state in the UI.
    """
    if user_override.strip():
        return user_override.strip()
    env = os.environ.get("TIDE_SPOTIFY_CLIENT_ID", "").strip()
    if env:
        return env
    return TIDE_DEFAULT_CLIENT_ID

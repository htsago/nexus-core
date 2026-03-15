from __future__ import annotations

import hashlib
import hmac
import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    RefreshToken,
)
from mcp.server.auth.routes import ClientRegistrationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from fastmcp.server.auth import OAuthProvider
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response
from starlette.routing import Route

from src.config import settings

# ── in-memory stores (process-scoped; reset on restart) ──────────────────────
_clients:        dict[str, OAuthClientInformationFull] = {}
_pending:        dict[str, tuple[OAuthClientInformationFull, AuthorizationParams]] = {}
_auth_codes:     dict[str, AuthorizationCode] = {}
_access_tokens:  dict[str, AccessToken]       = {}
_refresh_tokens: dict[str, RefreshToken]      = {}

_ACCESS_TTL  = 3600        # 1 hour
_REFRESH_TTL = 86400 * 30  # 30 days
_CODE_TTL    = 300          # 5 minutes


# ── consent page HTML ─────────────────────────────────────────────────────────

def _consent_html(sid: str, error: str | None = None) -> str:
    err_block = f'<p class="error">{error}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NEXUS — Authorize</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:system-ui,sans-serif;background:#0f1117;color:#e0e0e0;
         display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .card{{background:#1a1d27;border:1px solid #2e3148;border-radius:12px;
           padding:2.5rem;width:100%;max-width:420px;box-shadow:0 8px 32px #0006}}
    h1{{font-size:1.4rem;margin-bottom:.5rem;color:#fff}}
    p{{font-size:.9rem;color:#9aa;margin-bottom:1.5rem}}
    label{{display:block;font-size:.85rem;color:#bbb;margin-bottom:.4rem}}
    input[type=password]{{width:100%;padding:.7rem 1rem;border-radius:8px;
                          border:1px solid #3a3d55;background:#0f1117;
                          color:#fff;font-size:1rem;outline:none}}
    input[type=password]:focus{{border-color:#6c7bff}}
    button{{margin-top:1.2rem;width:100%;padding:.8rem;border-radius:8px;
            border:none;background:#6c7bff;color:#fff;font-size:1rem;
            cursor:pointer;font-weight:600}}
    button:hover{{background:#7d8eff}}
    .error{{color:#ff6b6b;font-size:.85rem;margin-bottom:1rem}}
    .logo{{text-align:center;font-size:2rem;margin-bottom:1.2rem}}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">⬡</div>
    <h1>NEXUS Core</h1>
    <p>Enter your API key to authorize access.</p>
    {err_block}
    <form method="POST" action="/consent">
      <input type="hidden" name="sid" value="{sid}">
      <label for="key">API Key</label>
      <input type="password" id="key" name="key" placeholder="••••••••••••••••" autofocus required>
      <button type="submit">Authorize</button>
    </form>
  </div>
</body>
</html>"""


# ── OAuth provider ────────────────────────────────────────────────────────────

class NexusOAuthProvider(OAuthProvider):
    """Full OAuth 2.0 Authorization Code + PKCE provider for NEXUS Core.

    Clients (e.g. Claude.ai) register dynamically, redirect to /consent where
    the user enters the NEXUS_API_KEY, and receive short-lived access tokens.
    All state is held in-process; tokens are lost on server restart.
    """

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.NEXUS_PUBLIC_URL,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                # Accept any scope (including "claudeai" used by Claude.ai)
                valid_scopes=None,
            ),
        )

    # ── dynamic client registration ───────────────────────────────────────────

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        _clients[client_info.client_id] = client_info

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return _clients.get(client_id)

    # ── authorization request → consent page ─────────────────────────────────

    async def authorize(
        self,
        client: OAuthClientInformationFull,
        params: AuthorizationParams,
    ) -> str:
        sid = secrets.token_urlsafe(24)
        _pending[sid] = (client, params)
        return f"/consent?sid={sid}"

    # ── consent route ─────────────────────────────────────────────────────────

    async def _consent_get(self, request: Request) -> Response:
        sid = request.query_params.get("sid", "")
        if sid not in _pending:
            return HTMLResponse("<h2>Invalid or expired authorization session.</h2>", status_code=400)
        return HTMLResponse(_consent_html(sid))

    async def _consent_post(self, request: Request) -> Response:
        form = await request.form()
        sid = str(form.get("sid", ""))
        key = str(form.get("key", ""))

        if sid not in _pending:
            return HTMLResponse("<h2>Invalid or expired authorization session.</h2>", status_code=400)

        client, params = _pending[sid]

        expected = settings.NEXUS_API_KEY
        valid = bool(expected) and hmac.compare_digest(
            hashlib.sha256(key.encode()).digest(),
            hashlib.sha256(expected.encode()).digest(),
        )
        if not valid:
            return HTMLResponse(_consent_html(sid, error="Incorrect API key — please try again."))

        del _pending[sid]

        code_value = secrets.token_urlsafe(32)
        _auth_codes[code_value] = AuthorizationCode(
            code=code_value,
            scopes=params.scopes or [],
            expires_at=time.time() + _CODE_TTL,
            client_id=client.client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
        )

        redirect = str(params.redirect_uri)
        sep = "&" if "?" in redirect else "?"
        redirect += f"{sep}code={code_value}"
        if params.state:
            redirect += f"&state={params.state}"
        return RedirectResponse(url=redirect, status_code=302, headers={"Cache-Control": "no-store"})

    async def _consent_dispatch(self, request: Request) -> Response:
        if request.method == "GET":
            return await self._consent_get(request)
        return await self._consent_post(request)

    def get_routes(self, mcp_path: str | None = None) -> list:
        routes = super().get_routes(mcp_path=mcp_path)
        routes.append(Route("/consent", endpoint=self._consent_dispatch, methods=["GET", "POST"]))
        return routes

    # ── authorization code exchange ───────────────────────────────────────────

    async def load_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: str,
    ) -> AuthorizationCode | None:
        code = _auth_codes.get(authorization_code)
        if code is None or code.client_id != client.client_id:
            return None
        if time.time() > code.expires_at:
            _auth_codes.pop(authorization_code, None)
            return None
        return code

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        _auth_codes.pop(authorization_code.code, None)

        access  = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(32)
        now     = int(time.time())

        _access_tokens[access] = AccessToken(
            token=access,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + _ACCESS_TTL,
        )
        _refresh_tokens[refresh] = RefreshToken(
            token=refresh,
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            expires_at=now + _REFRESH_TTL,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_ACCESS_TTL,
            refresh_token=refresh,
            scope=" ".join(authorization_code.scopes) or None,
        )

    # ── token loading ─────────────────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        # Accept the static API key directly — used by programmatic clients
        expected = settings.NEXUS_API_KEY
        if expected and hmac.compare_digest(
            hashlib.sha256(token.encode()).digest(),
            hashlib.sha256(expected.encode()).digest(),
        ):
            return AccessToken(token=token, client_id="static-key", scopes=[])

        # Otherwise validate an OAuth-issued access token.
        t = _access_tokens.get(token)
        if t is None:
            return None
        if t.expires_at is not None and time.time() > t.expires_at:
            _access_tokens.pop(token, None)
            return None
        return t

    async def load_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: str,
    ) -> RefreshToken | None:
        t = _refresh_tokens.get(refresh_token)
        if t is None or t.client_id != client.client_id:
            return None
        if t.expires_at is not None and time.time() > t.expires_at:
            _refresh_tokens.pop(refresh_token, None)
            return None
        return t

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        _refresh_tokens.pop(refresh_token.token, None)
        effective = scopes or refresh_token.scopes
        now       = int(time.time())
        access    = secrets.token_urlsafe(32)
        new_ref   = secrets.token_urlsafe(32)

        _access_tokens[access] = AccessToken(
            token=access,
            client_id=client.client_id,
            scopes=effective,
            expires_at=now + _ACCESS_TTL,
        )
        _refresh_tokens[new_ref] = RefreshToken(
            token=new_ref,
            client_id=client.client_id,
            scopes=effective,
            expires_at=now + _REFRESH_TTL,
        )
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=_ACCESS_TTL,
            refresh_token=new_ref,
            scope=" ".join(effective) or None,
        )

    # ── revocation ────────────────────────────────────────────────────────────

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        if isinstance(token, AccessToken):
            _access_tokens.pop(token.token, None)
        else:
            _refresh_tokens.pop(token.token, None)

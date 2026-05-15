"""Authentication endpoints.

Implements the Google OAuth 2.0 authorization-code flow with a short-lived,
signed JWT delivered to the frontend, an allow-list of accepted email
addresses and domains, and a rate-limited demo login used by the evaluation
tribunal to access the application without a Google account.
"""

import logging
import secrets
from ipaddress import ip_address
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import CurrentUser, DB
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import UserOut

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class DemoLoginRequest(BaseModel):
    """Request body for the demo-login endpoint.

    Carries the shared secret expected by the backend to grant a temporary
    session without going through Google OAuth.
    """

    code: str = Field(..., description="The secret demo access code")


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# Why: cookies are only marked Secure when the public backend URL is HTTPS,
# so local development over plain HTTP keeps working.
_is_https = settings.BACKEND_URL.startswith("https")


@router.get("/google", summary="Initiate Google OAuth login")
async def login_google():
    """Start the Google OAuth 2.0 authorization-code flow.

    Generates a random `state` value, stores it in an **HttpOnly** cookie to
    mitigate CSRF on the callback, and redirects the browser to Google's
    consent screen.

    Returns:
        RedirectResponse: 302 redirect pointing to Google's authorization URL.
    """
    state = secrets.token_urlsafe(32)
    redirect_uri = f"{settings.BACKEND_URL}/api/v1/auth/callback"

    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "offline",
    }

    redirect = RedirectResponse(url=f"{GOOGLE_AUTH_URL}?{urlencode(params)}")
    redirect.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=_is_https,
        samesite="lax",
        max_age=300,
    )
    return redirect


@router.get("/callback", summary="Google OAuth callback")
async def auth_callback(
    request: Request,
    db: DB,
    code: str,
    state: str,
    oauth_state: str | None = Cookie(default=None),
):
    """Handle the OAuth callback and issue an application JWT.

    Validates the `state` parameter against the cookie set during
    `/auth/google`, exchanges the authorization code for a Google access
    token, fetches the user profile, applies the configured email/domain
    allow-list, upserts the `User` row and finally redirects the browser to
    the frontend with a signed JWT in the query string.

    Args:
        request: Incoming FastAPI request (used for client metadata).
        db: Async SQLAlchemy session injected by `DB`.
        code: Authorization code returned by Google.
        state: Anti-CSRF state echoed back by Google.
        oauth_state: State value previously stored in the `oauth_state` cookie.

    Returns:
        RedirectResponse: 302 redirect to the frontend callback URL carrying
        the freshly minted JWT.

    Raises:
        HTTPException: **400** if the state mismatches (possible CSRF) or the
            token / userinfo exchange with Google fails.
        HTTPException: **403** if the authenticated email is not in the
            configured allow-list.
    """
    if not oauth_state or state != oauth_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state — possible CSRF attack")

    redirect_uri = f"{settings.BACKEND_URL}/api/v1/auth/callback"

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })

    if not token_resp.is_success:
        raise HTTPException(status_code=400, detail="Token exchange with Google failed")
    try:
        token_data = token_resp.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid response from Google token endpoint")
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to obtain access token from Google")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if not userinfo_resp.is_success:
        raise HTTPException(status_code=400, detail="Userinfo request to Google failed")
    try:
        user_info = userinfo_resp.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid response from Google userinfo endpoint")
    email: str = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email from Google")

    # Why: "*" acts as a wildcard for local/dev environments; in production the
    # list contains either full addresses or "@domain.com" suffix patterns.
    allowed = False
    if settings.ALLOWED_EMAILS == ["*"]:
        allowed = True
    else:
        for pattern in settings.ALLOWED_EMAILS:
            if pattern.startswith("@") and email.endswith(pattern):
                allowed = True
                break
            if email == pattern:
                allowed = True
                break

    if not allowed:
        logger.warning(f"Restricted access attempt by: {email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Your email or domain is not in the allow-list."
        )

    name: str = user_info.get("name", email)
    avatar_url: str | None = user_info.get("picture")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Why: upsert pattern — first login creates the row, subsequent logins
    # refresh the profile fields with the latest values returned by Google.
    if not user:
        user = User(email=email, name=name, avatar_url=avatar_url)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        user.name = name
        user.avatar_url = avatar_url
        await db.commit()

    jwt_token = create_access_token(str(user.id))

    redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/api/auth/callback?token={jwt_token}"
    )
    redirect.delete_cookie("oauth_state")
    return redirect


@router.post("/logout", summary="Invalidate session")
async def logout(response: Response):
    """Clear the authentication cookie on the client.

    The JWT is stateless on the server side, so logout simply deletes the
    `access_token` cookie from the browser.

    Returns:
        dict: A confirmation message.
    """
    response.delete_cookie(
        key="access_token",
        path="/",
        secure=_is_https,
        samesite="lax",
        httponly=True,
    )
    return {"message": "Logged out successfully"}


@router.post("/demo-login", summary="Login with a secret demo code")
async def demo_login(request: Request, body: DemoLoginRequest, db: DB):
    """Authenticate the evaluation tribunal via a shared secret code.

    Bypasses Google OAuth so the project can be demonstrated without
    provisioning Google accounts. Protected by an IP-based rate limit
    (**5 attempts per 15 minutes**) backed by Redis; loopback and Docker
    bridge addresses are exempt to keep automated tests and local
    `docker compose` runs working.

    Args:
        request: Incoming request — used to extract the client IP.
        body: Payload carrying the demo access code.
        db: Async SQLAlchemy session injected by `DB`.

    Returns:
        dict: An object with a single `token` field holding the JWT.

    Raises:
        HTTPException: **429** when the rate limit is exceeded.
        HTTPException: **401** when the supplied code is missing or wrong.
    """
    ip = request.client.host if request.client else "unknown"
    # Why: Docker bridge gateways appear as the client IP when the frontend
    # container calls the backend container during local development.
    docker_local_gateways = {"172.17.0.1", "172.18.0.1", "172.19.0.1", "host.docker.internal"}
    is_local = ip == "localhost" or ip in docker_local_gateways
    if not is_local:
        # Why: `ip_address(...)` raises a plain `ValueError` (not
        # `AddressValueError`) when `ip` is something like "unknown",
        # so we catch the parent class to handle every parse failure.
        try:
            is_local = ip_address(ip).is_loopback
        except ValueError:
            is_local = False
    # Why: deferred import to avoid a circular dependency between the auth
    # router and the cache service at module load time.
    from app.services.cache_service import is_rate_limited
    if not is_local and await is_rate_limited(f"demo_login:{ip}", limit=5, window=900):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many attempts. Please wait 15 minutes."
        )

    if not settings.DEMO_ACCESS_CODE or body.code != settings.DEMO_ACCESS_CODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or unconfigured demo access code."
        )

    demo_email = "usuario.demo@demo.local"
    result = await db.execute(select(User).where(User.email == demo_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=demo_email,
            name="Usuario Demo",
            avatar_url="https://api.dicebear.com/7.x/bottts/svg?seed=demo"
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    jwt_token = create_access_token(str(user.id))
    return {"token": jwt_token}


@router.get("/me", response_model=UserOut, summary="Get current user profile")
async def get_me(current_user: CurrentUser):
    """Return the profile of the currently authenticated user.

    The user is resolved from the JWT validated by the `CurrentUser`
    dependency; this endpoint is typically used by the frontend right after
    login to hydrate the session state.

    Returns:
        UserOut: The authenticated user's public profile.
    """
    return current_user

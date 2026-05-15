"""Authentication API Module.

Implements Google OAuth 2.0 stateless flow utilizing signed short-lived HttpOnly cookies, 
enterprise domain whitelisting filters, and secure session tear-down. Supports a 
throttled academic 'demo-login' endpoint restricted via dynamic Redis-backed IP limits.
"""

import logging
import secrets
from ipaddress import AddressValueError, ip_address
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import CurrentUser, DB
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import UserOut
from pydantic import BaseModel, Field

router = APIRouter(prefix="/auth", tags=["Authentication"])

class DemoLoginRequest(BaseModel):
    """Validates internal evaluation-only bypass payload schemas."""
    code: str = Field(..., description="The secret demo access code")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_is_https = settings.BACKEND_URL.startswith("https")


@router.get("/google", summary="Initiate Google OAuth login")
async def login_google():
    """Starts three-legged OAuth2 authorization code grant workflows.

    Creates random unguessable tokens saved into cryptographic cookies countering
    potential Cross-Site Request Forgery (CSRF) vectors.

    Returns:
        RedirectResponse: Directs browsers toward Google's identity confirmation screen.
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
    """Terminates authorization codes exchanged for Bearer tokens.

    Inspects incoming state strings against generated cookies, parses claim
    information from Google servers, registers persistent User records, and issues 
    a secured JWT redirecting identities toward the core application.

    Raises:
        HTTPException (400): Handled upon state mismatches or token endpoint failures.
        HTTPException (403): Triggered when identities conflict with configured domain bounds.
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

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to obtain access token from Google")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    user_info = userinfo_resp.json()
    email: str = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Could not retrieve email from Google")

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
            detail="Acceso restringido. Tu correo o dominio no está en la lista de permitidos."
        )

    name: str = user_info.get("name", email)
    avatar_url: str | None = user_info.get("picture")

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

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
    """Instructs user browsers to prune the authentication JWT cookie payload."""
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
    """Authorizes temporary evaluation logins bypassing OAuth constraints.

    Restricted via dynamic token-bucket throttling (max 5 tries / 15 mins) protecting
    endpoints against sequential brute-force, exempting local loopback traffic patterns.

    Raises:
        HTTPException (429): Triggered when dynamic rates violate security constraints.
        HTTPException (401): Supplied when incorrect passcodes are received.
    """
    ip = request.client.host if request.client else "unknown"
    docker_local_gateways = {"172.17.0.1", "172.18.0.1", "172.19.0.1", "host.docker.internal"}
    is_local = ip == "localhost" or ip in docker_local_gateways
    if not is_local:
        try:
            is_local = ip_address(ip).is_loopback
        except AddressValueError:
            is_local = False
    from app.services.cache_service import is_rate_limited
    if not is_local and await is_rate_limited(f"demo_login:{ip}", limit=5, window=900):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Por favor, espera 15 minutos."
        )

    if not settings.DEMO_ACCESS_CODE or body.code != settings.DEMO_ACCESS_CODE:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Código de acceso incorrecto o no configurado."
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
    """Validates active JWT scopes resolving the current operator profile."""
    return current_user

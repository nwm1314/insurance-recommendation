import ipaddress
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models.auth import User
from backend.app.services.auth_service import decode_access_token, get_user_permissions

security = HTTPBearer(auto_error=False)

ACCESS_TOKEN_COOKIE = "access_token"


def _extract_access_token(
    credentials: HTTPAuthorizationCredentials | None,
    request: Request,
) -> str | None:
    """Extract access token from http-only cookie, falling back to Authorization header."""
    cookie_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
    if cookie_token:
        return cookie_token
    if credentials and credentials.credentials:
        return credentials.credentials
    return None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    request: Request = None,
    db: Session = Depends(get_db),
) -> User:
    token = _extract_access_token(credentials, request)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == int(user_id)).first() if user_id else None
    if user is None or not user.is_active or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


def get_optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    request: Request = None,
    db: Session = Depends(get_db),
) -> User | None:
    token = _extract_access_token(credentials, request)
    if token is None:
        return None
    try:
        return get_current_user(credentials, request, db)
    except HTTPException:
        return None


def require_permission(permission: str):
    def dependency(user: User = Depends(get_current_user)) -> User:
        if permission not in get_user_permissions(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return user
    return dependency


def _peer_is_trusted_proxy(request: Request) -> bool:
    """True only when proxy-header parsing is enabled and the direct peer
    address is inside the configured trusted proxy list."""
    if not settings.trust_proxy_headers:
        return False
    peer = request.client.host if request.client else None
    if not peer:
        return False
    try:
        peer_addr = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(peer_addr in network for network in settings.parsed_trusted_proxies)


def _is_trusted_address(address: str) -> bool:
    try:
        addr = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(addr in network for network in settings.parsed_trusted_proxies)


def _first_untrusted_forwarded_for(request: Request) -> str | None:
    """Walk X-Forwarded-For from the right: trusted proxies append the peer
    address, so the first non-proxy, syntactically valid IP is the client."""
    xff = request.headers.get("x-forwarded-for")
    if not xff:
        return None
    entries = [entry.strip() for entry in xff.split(",") if entry.strip()]
    for entry in reversed(entries):
        if _is_trusted_address(entry):
            continue
        try:
            ipaddress.ip_address(entry)
        except ValueError:
            continue
        return entry
    return None


def get_client_ip(request: Request) -> str | None:
    """Resolve the client IP for audit logs. X-Forwarded-For is honored only
    when the direct peer is a configured trusted proxy; otherwise the direct
    connection address is used and client-controlled headers are ignored."""
    if _peer_is_trusted_proxy(request):
        forwarded = _first_untrusted_forwarded_for(request)
        if forwarded:
            return forwarded
    return request.client.host if request.client else None
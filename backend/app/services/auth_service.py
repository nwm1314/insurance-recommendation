from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import bcrypt
import jwt
from sqlalchemy.orm import Session
from backend.app.config import settings
from backend.app.time import utc_now
from backend.app.models.auth import (
    AuditLog,
    Permission,
    RecommendationRecord,
    RefreshToken,
    Role,
    RolePermission,
    SavedProfile,
    User,
    UserRole,
)

DEFAULT_PERMISSIONS = [
    "product:read",
    "crawl:read",
    "crawl:trigger",
    "review:read",
    "review:approve",
    "audit:read",
    "recommendation:read_self",
    "profile:save_self",
]

ROLE_PERMISSIONS = {
    "user": ["recommendation:read_self", "profile:save_self"],
    "admin": DEFAULT_PERMISSIONS,
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "iat": now,
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def create_refresh_token(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = utc_now() + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(token), expires_at=expires_at))
    db.commit()
    return token


def get_user_roles(user: User) -> list[str]:
    return [user_role.role.name for user_role in user.roles]


def get_user_permissions(user: User) -> list[str]:
    permissions: set[str] = set()
    for user_role in user.roles:
        for role_permission in user_role.role.permissions:
            permissions.add(role_permission.permission.name)
    return sorted(permissions)


def serialize_user(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "roles": get_user_roles(user),
        "permissions": get_user_permissions(user),
    }


def ensure_auth_defaults(db: Session):
    permission_by_name: dict[str, Permission] = {}
    for permission_name in DEFAULT_PERMISSIONS:
        permission = db.query(Permission).filter(Permission.name == permission_name).first()
        if permission is None:
            permission = Permission(name=permission_name)
            db.add(permission)
        permission_by_name[permission_name] = permission

    role_by_name: dict[str, Role] = {}
    for role_name in ROLE_PERMISSIONS:
        role = db.query(Role).filter(Role.name == role_name).first()
        if role is None:
            role = Role(name=role_name)
            db.add(role)
        role_by_name[role_name] = role

    db.flush()

    for role_name, permission_names in ROLE_PERMISSIONS.items():
        role = role_by_name[role_name]
        existing_ids = {role_permission.permission_id for role_permission in role.permissions}
        for permission_name in permission_names:
            permission = permission_by_name[permission_name]
            if permission.id not in existing_ids:
                db.add(RolePermission(role_id=role.id, permission_id=permission.id))

    if settings.first_admin_password:
        admin = db.query(User).filter(User.email == settings.first_admin_email).first()
        if admin is None:
            admin = User(
                email=settings.first_admin_email,
                password_hash=hash_password(settings.first_admin_password),
                full_name="Admin",
            )
            db.add(admin)
            db.flush()
            db.add(UserRole(user_id=admin.id, role_id=role_by_name["admin"].id))

    db.commit()


def create_user(db: Session, email: str, password: str, full_name: str | None = None) -> User:
    existing_user = db.query(User).filter(User.email == email.lower()).first()
    if existing_user:
        raise ValueError("email_exists")

    has_users = db.query(User.id).first() is not None
    role_name = "user" if has_users else "admin"
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        ensure_auth_defaults(db)
        role = db.query(Role).filter(Role.name == role_name).first()

    user = User(email=email.lower(), password_hash=hash_password(password), full_name=full_name)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = db.query(User).filter(User.email == email.lower()).first()
    if not user or not user.is_active or user.status != "active":
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def rotate_refresh_token(db: Session, refresh_token: str) -> tuple[User, str] | None:
    token_hash = hash_token(refresh_token)
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if not stored or stored.revoked_at or stored.expires_at < utc_now():
        return None

    stored.revoked_at = utc_now()
    db.flush()
    new_token = create_refresh_token(db, stored.user)
    return stored.user, new_token


def revoke_refresh_token(db: Session, refresh_token: str | None):
    if not refresh_token:
        return
    stored = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(refresh_token)).first()
    if stored and not stored.revoked_at:
        stored.revoked_at = utc_now()
        db.commit()


def write_audit_log(
    db: Session,
    user: User | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
):
    db.add(AuditLog(
        user_id=user.id if user else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    ))
    db.commit()


def save_recommendation_record(db: Session, user: User, profile: dict, result: dict):
    db.add(RecommendationRecord(user_id=user.id, profile=profile, result=result))
    db.commit()


def save_profile(db: Session, user: User, name: str, profile: dict, note: str | None = None) -> SavedProfile:
    saved = SavedProfile(user_id=user.id, name=name, profile=profile, note=note)
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved

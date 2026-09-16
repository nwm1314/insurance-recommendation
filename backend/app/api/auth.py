from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
import logging
import redis as redis_lib
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import ACCESS_TOKEN_COOKIE, get_client_ip, get_current_user, require_permission
from backend.app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RecommendationRecordCreate,
    RefreshRequest,
    RegisterRequest,
    RoleUpdateRequest,
    SavedProfileRequest,
    UserPublic,
)
from backend.app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    get_user_roles,
    revoke_refresh_token,
    rotate_refresh_token,
    save_profile,
    serialize_user,
    set_user_roles,
    write_audit_log,
)
from backend.app.models.auth import RecommendationRecord, SavedProfile, User
from backend.app.config import settings

router = APIRouter(prefix="/api", tags=["auth"])

REFRESH_TOKEN_COOKIE = "refresh_token"

logger = logging.getLogger(__name__)

# OPS-002：登录防爆破（Redis 计数，故障 fail-open）。失败按邮箱与 IP 双维
# 计数；达到阈值返回 429，成功登录清零。
LOGIN_FAIL_THRESHOLD = 5
LOGIN_FAIL_TTL_SECONDS = 900  # 15 分钟


def _get_redis_client():
    try:
        client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


def _login_bruteforce_check(client, email: str, ip: str) -> bool:
    """登录前检查失败计数；达到阈值返回 False（拒绝）。"""
    for key in (f"login_fail:{email}", f"login_fail_ip:{ip}"):
        try:
            current = client.get(key)
            if current is not None and int(current) >= LOGIN_FAIL_THRESHOLD:
                return False
        except Exception:
            return True
    return True


def _record_login_failure(client, email: str, ip: str) -> None:
    for key in (f"login_fail:{email}", f"login_fail_ip:{ip}"):
        try:
            value = client.incr(key)
            if value == 1:
                client.expire(key, LOGIN_FAIL_TTL_SECONDS)
        except Exception as exc:
            logger.warning("login failure counting skipped: %s", exc)
            return


def _clear_login_failures(client, email: str, ip: str) -> None:
    try:
        client.delete(f"login_fail:{email}")
        client.delete(f"login_fail_ip:{ip}")
    except Exception:
        pass


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str):
    """Set access and refresh tokens as http-only cookies."""
    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE,
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/",
    )


def _clear_auth_cookies(response: Response):
    response.delete_cookie(key=ACCESS_TOKEN_COOKIE, path="/")
    response.delete_cookie(key=REFRESH_TOKEN_COOKIE, path="/")


def _serialize_user_response(user: User) -> dict:
    return UserPublic(**serialize_user(user)).model_dump()


@router.post("/auth/register", response_model=UserPublic)
def register(
    response: Response,
    request: RegisterRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    try:
        user = create_user(db, request.email, request.password, request.full_name)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(db, user)
    _set_auth_cookies(response, access_token, refresh_token)
    write_audit_log(db, user, "auth.register", "user", str(user.id), ip_address=get_client_ip(raw_request))
    return UserPublic(**serialize_user(user))


@router.post("/auth/login", response_model=UserPublic)
def login(
    response: Response,
    request: LoginRequest,
    raw_request: Request,
    db: Session = Depends(get_db),
):
    client_ip = get_client_ip(raw_request) or "unknown"
    # OPS-002：防爆破——Redis 不可用时跳过（fail-open），不阻塞正常登录
    redis_client = _get_redis_client()
    if redis_client is not None and not _login_bruteforce_check(redis_client, request.email, client_ip):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="尝试过于频繁，请15分钟后再试")

    user = authenticate_user(db, request.email, request.password)
    if user is None:
        if redis_client is not None:
            _record_login_failure(redis_client, request.email, client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    if redis_client is not None:
        _clear_login_failures(redis_client, request.email, client_ip)
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(db, user)
    _set_auth_cookies(response, access_token, refresh_token)
    write_audit_log(db, user, "auth.login", "user", str(user.id), ip_address=get_client_ip(raw_request))
    return UserPublic(**serialize_user(user))


@router.post("/auth/refresh", response_model=UserPublic)
def refresh(
    response: Response,
    request: Request,
    db: Session = Depends(get_db),
):
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少刷新令牌")
    rotated = rotate_refresh_token(db, refresh_token)
    if rotated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
    user, new_refresh_token = rotated
    access_token = create_access_token(user)
    _set_auth_cookies(response, access_token, new_refresh_token)
    return UserPublic(**serialize_user(user))


@router.post("/auth/logout")
def logout(
    response: Response,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    revoke_refresh_token(db, refresh_token)
    write_audit_log(db, user, "auth.logout", "user", str(user.id))
    _clear_auth_cookies(response)
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return UserPublic(**serialize_user(user))


@router.post("/admin/users/{user_id}/roles", response_model=UserPublic)
def update_user_roles(
    user_id: int,
    request: RoleUpdateRequest,
    raw_request: Request,
    actor: User = Depends(require_permission("admin:grant")),
    db: Session = Depends(get_db),
):
    target = db.query(User).filter(User.id == user_id).first()
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    old_roles = get_user_roles(target)
    try:
        set_user_roles(db, target, request.roles, actor)
    except ValueError as exc:
        if str(exc) == "cannot_revoke_self_admin":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能移除自己的管理员角色")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效角色")
    write_audit_log(
        db,
        actor,
        "admin.roles.update",
        "user",
        str(target.id),
        detail={"from": old_roles, "to": get_user_roles(target)},
        ip_address=get_client_ip(raw_request),
    )
    return UserPublic(**serialize_user(target))


@router.get("/my/recommendations")
def my_recommendations(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    records = (
        db.query(RecommendationRecord)
        .filter(RecommendationRecord.user_id == user.id)
        .order_by(RecommendationRecord.created_at.desc())
        .limit(50)
        .all()
    )
    return {"records": [
        {
            "id": record.id,
            "profile": record.profile,
            "result": record.result,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }
        for record in records
    ]}


@router.get("/my/recommendations/{record_id}")
def get_recommendation_detail(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """返回完整推荐记录。result.meta 携带复现元数据（DATA-002）：

    - 按 result.meta.scoring_weights_hash 检出对应的 scoring_weights.yaml；
    - 按 result 中的 product_id 与记录 created_at 查 ProductVersion，
      即可还原当时的评分口径与产品事实，复现推荐结果。
    """
    record = (
        db.query(RecommendationRecord)
        .filter(RecommendationRecord.id == record_id, RecommendationRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推荐记录不存在")
    return {
        "id": record.id,
        "profile": record.profile,
        "result": record.result,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


@router.get("/my/profiles/{profile_id}")
def get_profile_detail(
    profile_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(SavedProfile)
        .filter(SavedProfile.id == profile_id, SavedProfile.user_id == user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像不存在")
    return {
        "id": profile.id,
        "name": profile.name,
        "profile": profile.profile,
        "note": profile.note,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


@router.post("/my/recommendations")
def create_recommendation_record(
    request: RecommendationRecordCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = RecommendationRecord(
        user_id=user.id,
        profile=request.profile,
        result=request.result,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {"id": record.id, "created_at": record.created_at.isoformat() if record.created_at else None}


@router.post("/my/profiles")
def create_saved_profile(
    request: SavedProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = save_profile(db, user, request.name, request.profile, request.note)
    return {"id": saved.id, "name": saved.name, "created_at": saved.created_at.isoformat() if saved.created_at else None}



@router.delete("/my/recommendations/{record_id}")
def delete_recommendation(
    record_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(RecommendationRecord)
        .filter(RecommendationRecord.id == record_id, RecommendationRecord.user_id == user.id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="推荐记录不存在")
    db.delete(record)
    db.commit()
    return {"status": "ok"}


@router.delete("/my/profiles/{profile_id}")
def delete_profile(
    profile_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(SavedProfile)
        .filter(SavedProfile.id == profile_id, SavedProfile.user_id == user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像不存在")
    db.delete(profile)
    db.commit()
    return {"status": "ok"}


@router.put("/my/profiles/{profile_id}")
def update_profile(
    profile_id: int,
    request: SavedProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = (
        db.query(SavedProfile)
        .filter(SavedProfile.id == profile_id, SavedProfile.user_id == user.id)
        .first()
    )
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="画像不存在")
    profile.name = request.name
    profile.profile = request.profile
    profile.note = request.note
    db.commit()
    db.refresh(profile)
    return {
        "id": profile.id,
        "name": profile.name,
        "profile": profile.profile,
        "note": profile.note,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }

@router.get("/my/profiles")
def my_profiles(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profiles = (
        db.query(SavedProfile)
        .filter(SavedProfile.user_id == user.id)
        .order_by(SavedProfile.created_at.desc())
        .all()
    )
    return {"profiles": [
        {
            "id": profile.id,
            "name": profile.name,
            "profile": profile.profile,
            "note": profile.note,
            "created_at": profile.created_at.isoformat() if profile.created_at else None,
        }
        for profile in profiles
    ]}
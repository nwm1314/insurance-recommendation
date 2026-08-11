from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
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
    user = authenticate_user(db, request.email, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
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
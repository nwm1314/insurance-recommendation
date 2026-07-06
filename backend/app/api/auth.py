from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from backend.app.database import get_db
from backend.app.dependencies.auth import get_client_ip, get_current_user
from backend.app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    SavedProfileRequest,
    TokenResponse,
    UserPublic,
)
from backend.app.services.auth_service import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    create_user,
    revoke_refresh_token,
    rotate_refresh_token,
    save_profile,
    serialize_user,
    write_audit_log,
)
from backend.app.models.auth import RecommendationRecord, SavedProfile, User

router = APIRouter(prefix="/api", tags=["auth"])


def _token_response(db: Session, user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=create_refresh_token(db, user),
        user=UserPublic(**serialize_user(user)),
    )


@router.post("/auth/register", response_model=TokenResponse)
def register(request: RegisterRequest, raw_request: Request, db: Session = Depends(get_db)):
    try:
        user = create_user(db, request.email, request.password, request.full_name)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="邮箱已注册")
    write_audit_log(db, user, "auth.register", "user", str(user.id), ip_address=get_client_ip(raw_request))
    return _token_response(db, user)


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, raw_request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, request.email, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="邮箱或密码错误")
    write_audit_log(db, user, "auth.login", "user", str(user.id), ip_address=get_client_ip(raw_request))
    return _token_response(db, user)


@router.post("/auth/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, db: Session = Depends(get_db)):
    rotated = rotate_refresh_token(db, request.refresh_token)
    if rotated is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="刷新令牌无效")
    user, new_refresh_token = rotated
    return TokenResponse(
        access_token=create_access_token(user),
        refresh_token=new_refresh_token,
        user=UserPublic(**serialize_user(user)),
    )


@router.post("/auth/logout")
def logout(request: LogoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    revoke_refresh_token(db, request.refresh_token)
    write_audit_log(db, user, "auth.logout", "user", str(user.id))
    return {"status": "ok"}


@router.get("/auth/me", response_model=UserPublic)
def me(user: User = Depends(get_current_user)):
    return UserPublic(**serialize_user(user))


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


@router.post("/my/profiles")
def create_saved_profile(
    request: SavedProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = save_profile(db, user, request.name, request.profile, request.note)
    return {"id": saved.id, "name": saved.name, "created_at": saved.created_at.isoformat() if saved.created_at else None}


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

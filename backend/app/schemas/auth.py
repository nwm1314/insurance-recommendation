from pydantic import BaseModel, EmailStr, Field


class UserPublic(BaseModel):
    id: int
    email: str
    full_name: str | None = None
    roles: list[str] = []
    permissions: list[str] = []


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserPublic


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class SavedProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    profile: dict
    note: str | None = None
class RecommendationRecordCreate(BaseModel):
    profile: dict
    result: dict


class RoleUpdateRequest(BaseModel):
    roles: list[str]

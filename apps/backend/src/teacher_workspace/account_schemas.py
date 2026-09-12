from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

Password = Annotated[str, Field(min_length=12, max_length=200)]
CURRENT_PRIVACY_NOTICE_VERSION = "2026-09-11"


class RegisterRequest(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,39}$")
    password: Password
    password_confirmation: Password
    privacy_notice_accepted: Literal[True]
    privacy_notice_version: Literal["2026-09-11"]
    invite_code: str | None = Field(default=None, min_length=20, max_length=200)

    @model_validator(mode="after")
    def matching_passwords(self) -> "RegisterRequest":
        if self.password != self.password_confirmation:
            raise ValueError("Passwords do not match")
        if self.password.isspace():
            raise ValueError("Password cannot be blank")
        return self


class RecoveryResponse(BaseModel):
    recovery_code: str


class RegisterResponse(RecoveryResponse):
    username: str


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: Password


class ConfirmPasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)


class AccountDeletionRequest(ConfirmPasswordRequest):
    confirm_username: str = Field(min_length=1, max_length=100)


class AccountDeletionStatus(BaseModel):
    scheduled_for: datetime


class ResetPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    recovery_code: str = Field(min_length=20, max_length=128)
    new_password: Password


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    is_current: bool


class RegistrationConfig(BaseModel):
    enabled: bool
    invite_required: bool = False
    privacy_notice_version: str = CURRENT_PRIVACY_NOTICE_VERSION
    support_contact: str | None = None


class StorageUsageResponse(BaseModel):
    used_bytes: int
    quota_bytes: int
    remaining_bytes: int

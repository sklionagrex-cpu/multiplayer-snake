from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


# ---------- Пользователь ----------
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=4, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        orm_mode = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Миры ----------
class WorldCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str = ""
    max_players: int = Field(5, ge=2, le=10)


class WorldUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    player_count: Optional[int] = None
    is_active: Optional[bool] = None
    host_ip: Optional[str] = None
    host_port: Optional[int] = None


class WorldOut(BaseModel):
    id: int
    name: str
    description: str
    owner_id: int
    owner_username: str
    is_active: bool
    player_count: int
    max_players: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

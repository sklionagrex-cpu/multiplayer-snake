from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from database import engine, get_db, Base
from models import User, World
from schemas import (
    UserCreate, UserLogin, UserOut, Token,
    WorldCreate, WorldUpdate, WorldOut,
)
from auth import (
    create_user, authenticate_user, create_access_token,
    get_current_user, get_user_by_username,
)

# Создаём таблицы
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Multiplayer Snake",
    description="Лаунчер мультиплеера для Minecraft PE 1.1.5",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== АВТОРИЗАЦИЯ ==========

@app.post("/register", response_model=Token, tags=["Авторизация"])
def register(user: UserCreate, db: Session = Depends(get_db)):
    """Регистрация нового пользователя"""
    if get_user_by_username(db, user.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким ником уже существует",
        )
    db_user = create_user(db, user)
    token = create_access_token(data={"sub": db_user.username})
    return Token(
        access_token=token,
        user=UserOut.from_orm(db_user),
    )


@app.post("/login", response_model=Token, tags=["Авторизация"])
def login(user: UserLogin, db: Session = Depends(get_db)):
    """Вход в аккаунт"""
    db_user = authenticate_user(db, user.username, user.password)
    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный ник или пароль",
        )
    token = create_access_token(data={"sub": db_user.username})
    return Token(
        access_token=token,
        user=UserOut.from_orm(db_user),
    )


@app.get("/me", response_model=UserOut, tags=["Авторизация"])
def get_me(current_user: User = Depends(get_current_user)):
    """Текущий пользователь"""
    return current_user


# ========== МИРЫ ==========

@app.get("/worlds", response_model=List[WorldOut], tags=["Миры"])
def list_worlds(db: Session = Depends(get_db)):
    """Список всех активных миров"""
    worlds = (
        db.query(World)
        .filter(World.is_active == True)
        .order_by(World.updated_at.desc())
        .all()
    )
    result = []
    for w in worlds:
        result.append(WorldOut(
            id=w.id,
            name=w.name,
            description=w.description or "",
            owner_id=w.owner_id,
            owner_username=w.owner.username if w.owner else "Неизвестно",
            is_active=w.is_active,
            player_count=w.player_count,
            max_players=w.max_players,
            created_at=w.created_at,
            updated_at=w.updated_at,
        ))
    return result


@app.post("/worlds", response_model=WorldOut, tags=["Миры"])
def create_world(
    world: WorldCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Создать / открыть мир (стать хостом)"""
    # Закрываем предыдущие активные миры этого пользователя
    db.query(World).filter(
        World.owner_id == current_user.id,
        World.is_active == True,
    ).update({"is_active": False})

    db_world = World(
        name=world.name,
        description=world.description,
        owner_id=current_user.id,
        max_players=world.max_players,
        player_count=1,
        is_active=True,
    )
    db.add(db_world)
    db.commit()
    db.refresh(db_world)

    return WorldOut(
        id=db_world.id,
        name=db_world.name,
        description=db_world.description or "",
        owner_id=db_world.owner_id,
        owner_username=current_user.username,
        is_active=db_world.is_active,
        player_count=db_world.player_count,
        max_players=db_world.max_players,
        created_at=db_world.created_at,
        updated_at=db_world.updated_at,
    )


@app.patch("/worlds/{world_id}", response_model=WorldOut, tags=["Миры"])
def update_world(
    world_id: int,
    data: WorldUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Обновить мир (только владелец)"""
    world = db.query(World).filter(World.id == world_id).first()
    if not world:
        raise HTTPException(status_code=404, detail="Мир не найден")
    if world.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на этот мир")

    for field, value in data.dict(exclude_unset=True).items():
        setattr(world, field, value)

    db.commit()
    db.refresh(world)

    return WorldOut(
        id=world.id,
        name=world.name,
        description=world.description or "",
        owner_id=world.owner_id,
        owner_username=current_user.username,
        is_active=world.is_active,
        player_count=world.player_count,
        max_players=world.max_players,
        created_at=world.created_at,
        updated_at=world.updated_at,
    )


@app.delete("/worlds/{world_id}", tags=["Миры"])
def close_world(
    world_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Закрыть мир (сделать неактивным)"""
    world = db.query(World).filter(World.id == world_id).first()
    if not world:
        raise HTTPException(status_code=404, detail="Мир не найден")
    if world.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет прав на этот мир")

    world.is_active = False
    db.commit()
    return {"ok": True, "message": "Мир закрыт"}


@app.get("/")
def root():
    return {
        "name": "Multiplayer Snake",
        "version": "0.1.0",
        "description": "Лаунчер мультиплеера для Minecraft PE 1.1.5",
        "docs": "/docs",
    }

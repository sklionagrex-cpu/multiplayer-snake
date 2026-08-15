"""
Multiplayer Snake — бэкенд (Flask)
Лаунчер мультиплеера для Minecraft PE 1.1.5
"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import os

from flask import Flask, request, jsonify
from flask_cors import CORS
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/neondb")
SECRET_KEY = os.getenv("SECRET_KEY", "multiplayer-snake-secret-key-change-me-2026")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7

db_url = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")
if db_url.startswith("postgresql://") and "+pg8000" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = Flask(__name__)
CORS(app)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    worlds = relationship("World", back_populates="owner")


class World(Base):
    __tablename__ = "worlds"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, default="")
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    player_count = Column(Integer, default=1)
    max_players = Column(Integer, default=5)
    host_ip = Column(String(100), nullable=True)
    host_port = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="worlds")


Base.metadata.create_all(bind=engine)


def get_db():
    return SessionLocal()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_token(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": username, "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def user_to_dict(u: User) -> dict:
    return {
        "id": u.id,
        "username": u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def world_to_dict(w: World) -> dict:
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description or "",
        "owner_id": w.owner_id,
        "owner_username": w.owner.username if w.owner else "Неизвестно",
        "is_active": w.is_active,
        "player_count": w.player_count,
        "max_players": w.max_players,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"detail": "Нужен токен"}), 401
        token = auth[7:]
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if not username:
                return jsonify({"detail": "Неверный токен"}), 401
        except JWTError:
            return jsonify({"detail": "Неверный токен"}), 401

        db = get_db()
        user = db.query(User).filter(User.username == username).first()
        if not user:
            db.close()
            return jsonify({"detail": "Пользователь не найден"}), 401
        return f(user, db, *args, **kwargs)

    return decorated


@app.get("/")
def root():
    return {
        "name": "Multiplayer Snake",
        "version": "0.2.0",
        "description": "Лаунчер мультиплеера для Minecraft PE 1.1.5",
    }


@app.post("/register")
def register():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if len(username) < 3:
        return jsonify({"detail": "Ник слишком короткий (мин. 3)"}), 400
    if len(password) < 4:
        return jsonify({"detail": "Пароль слишком короткий (мин. 4)"}), 400

    db = get_db()
    try:
        if db.query(User).filter(User.username == username).first():
            return jsonify({"detail": "Пользователь с таким ником уже существует"}), 400
        user = User(username=username, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_token(user.username)
        return jsonify({
            "access_token": token,
            "token_type": "bearer",
            "user": user_to_dict(user),
        })
    finally:
        db.close()


@app.post("/login")
def login():
    data = request.get_json() or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    db = get_db()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return jsonify({"detail": "Неверный ник или пароль"}), 401
        token = create_token(user.username)
        return jsonify({
            "access_token": token,
            "token_type": "bearer",
            "user": user_to_dict(user),
        })
    finally:
        db.close()


@app.get("/me")
@token_required
def me(user, db):
    try:
        return jsonify(user_to_dict(user))
    finally:
        db.close()


@app.get("/worlds")
def list_worlds():
    db = get_db()
    try:
        worlds = (
            db.query(World)
            .filter(World.is_active == True)
            .order_by(World.updated_at.desc())
            .all()
        )
        return jsonify([world_to_dict(w) for w in worlds])
    finally:
        db.close()


@app.post("/worlds")
@token_required
def create_world(user, db):
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    description = data.get("description") or ""
    max_players = int(data.get("max_players") or 5)

    if not name:
        db.close()
        return jsonify({"detail": "Название обязательно"}), 400
    max_players = max(2, min(10, max_players))

    try:
        db.query(World).filter(
            World.owner_id == user.id,
            World.is_active == True,
        ).update({"is_active": False})

        world = World(
            name=name,
            description=description,
            owner_id=user.id,
            max_players=max_players,
            player_count=1,
            is_active=True,
        )
        db.add(world)
        db.commit()
        db.refresh(world)
        _ = world.owner
        return jsonify(world_to_dict(world))
    finally:
        db.close()


@app.route("/worlds/<int:world_id>", methods=["PATCH"])
@token_required
def update_world(user, db, world_id):
    data = request.get_json() or {}
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world:
            return jsonify({"detail": "Мир не найден"}), 404
        if world.owner_id != user.id:
            return jsonify({"detail": "Нет прав на этот мир"}), 403

        if "name" in data and data["name"]:
            world.name = data["name"]
        if "description" in data:
            world.description = data["description"]
        if "player_count" in data:
            world.player_count = data["player_count"]
        if "is_active" in data:
            world.is_active = data["is_active"]
        if "host_ip" in data:
            world.host_ip = data["host_ip"]
        if "host_port" in data:
            world.host_port = data["host_port"]

        db.commit()
        db.refresh(world)
        _ = world.owner
        return jsonify(world_to_dict(world))
    finally:
        db.close()


@app.route("/worlds/<int:world_id>", methods=["DELETE"])
@token_required
def close_world(user, db, world_id):
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world:
            return jsonify({"detail": "Мир не найден"}), 404
        if world.owner_id != user.id:
            return jsonify({"detail": "Нет прав на этот мир"}), 403
        world.is_active = False
        db.commit()
        return jsonify({"ok": True, "message": "Мир закрыт"})
    finally:
        db.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)

"""
Multiplayer Snake — бэкенд (Flask, без тяжёлых зависимостей)
Работает в Termux / Python 3.14
"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import os
import hashlib
import hmac
import json
import base64
import secrets

from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func

# ---------- .env вручную (без python-dotenv) ----------
def load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

load_env()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:pass@localhost/neondb")
SECRET_KEY = os.getenv("SECRET_KEY", "multiplayer-snake-secret-key-change-me-2026")
TOKEN_DAYS = 7

db_url = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")
if db_url.startswith("postgresql://") and "+pg8000" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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


try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print("Предупреждение при создании таблиц:", e)


def get_db():
    return SessionLocal()


# ---------- Пароли (stdlib) ----------
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000)
    return salt + "$" + h.hex()


def verify_password(plain: str, stored: str) -> bool:
    try:
        salt, h = stored.split("$", 1)
        check = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt.encode(), 100_000).hex()
        return hmac.compare_digest(check, h)
    except Exception:
        return False


# ---------- Простой JWT (stdlib) ----------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(username: str) -> str:
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    exp = int((datetime.now(timezone.utc) + timedelta(days=TOKEN_DAYS)).timestamp())
    payload = _b64url(json.dumps({"sub": username, "exp": exp}).encode())
    sig = hmac.new(SECRET_KEY.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    return f"{header}.{payload}.{_b64url(sig)}"


def decode_token(token: str):
    try:
        header_b, payload_b, sig_b = token.split(".")
        expected = hmac.new(
            SECRET_KEY.encode(), f"{header_b}.{payload_b}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_b64url(expected), sig_b) and not hmac.compare_digest(expected, _b64url_decode(sig_b)):
            # compare raw
            if not hmac.compare_digest(expected, _b64url_decode(sig_b)):
                return None
        data = json.loads(_b64url_decode(payload_b))
        if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        return data
    except Exception:
        return None


def user_to_dict(u):
    return {
        "id": u.id,
        "username": u.username,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def world_to_dict(w):
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
        data = decode_token(auth[7:])
        if not data or not data.get("sub"):
            return jsonify({"detail": "Неверный токен"}), 401
        db = get_db()
        user = db.query(User).filter(User.username == data["sub"]).first()
        if not user:
            db.close()
            return jsonify({"detail": "Пользователь не найден"}), 401
        return f(user, db, *args, **kwargs)
    return decorated


@app.get("/")
def root():
    return {
        "name": "Multiplayer Snake",
        "version": "0.3.0",
        "description": "Лаунчер мультиплеера для Minecraft PE 1.1.5",
    }


@app.post("/register")
def register():
    data = request.get_json(silent=True) or {}
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
        return jsonify({
            "access_token": create_token(user.username),
            "token_type": "bearer",
            "user": user_to_dict(user),
        })
    finally:
        db.close()


@app.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    db = get_db()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user or not verify_password(password, user.password_hash):
            return jsonify({"detail": "Неверный ник или пароль"}), 401
        return jsonify({
            "access_token": create_token(user.username),
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
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    description = data.get("description") or ""
    max_players = int(data.get("max_players") or 5)
    if not name:
        db.close()
        return jsonify({"detail": "Название обязательно"}), 400
    max_players = max(2, min(10, max_players))
    try:
        db.query(World).filter(World.owner_id == user.id, World.is_active == True).update({"is_active": False})
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
    data = request.get_json(silent=True) or {}
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world:
            return jsonify({"detail": "Мир не найден"}), 404
        if world.owner_id != user.id:
            return jsonify({"detail": "Нет прав на этот мир"}), 403
        for key in ("name", "description", "player_count", "is_active", "host_ip", "host_port"):
            if key in data:
                setattr(world, key, data[key])
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
    print("Multiplayer Snake backend 0.3.0")
    print("http://0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000, debug=False)

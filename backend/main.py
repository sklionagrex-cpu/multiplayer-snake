"""
Multiplayer Snake — backend 0.4.0
Accounts, friends, avatars, bans, host presence
"""
from datetime import datetime, timedelta, timezone
from functools import wraps
import os
import hashlib
import hmac
import json
import base64
import secrets
import ssl as _ssl

from flask import Flask, request, jsonify
from flask_cors import CORS
from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Boolean,
    DateTime, ForeignKey, UniqueConstraint, or_, and_
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func

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

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
SECRET_KEY = os.getenv("SECRET_KEY", "multiplayer-snake-secret-key-change-me-2026")
TOKEN_DAYS = 7
HOST_TIMEOUT_SEC = 30  # world disappears if no heartbeat
PLAYER_TIMEOUT_SEC = 45  # player leaves list if no presence

AVATARS = [
    "snake_green", "snake_blue", "snake_red", "snake_gold",
    "creeper", "steve", "alex", "enderman", "diamond", "pickaxe"
]

def _normalize_db_url(url: str) -> str:
    if not url:
        return ""
    for junk in (
        "channel_binding=require", "channel_binding=prefer",
        "sslmode=require", "sslmode=prefer", "sslmode=verify-full",
        "sslmode=verify-ca", "ssl=true",
    ):
        url = url.replace("&" + junk, "").replace("?" + junk, "?")
    url = url.replace("?&", "?").rstrip("?&")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://") and "+pg8000" not in url:
        url = url.replace("postgresql://", "postgresql+pg8000://", 1)
    return url

db_url = _normalize_db_url(DATABASE_URL)
DB_OK = False
DB_ERROR = None
engine = None
SessionLocal = None

if not db_url:
    DB_ERROR = "DATABASE_URL не задан"
    print("CRITICAL:", DB_ERROR)
else:
    try:
        ssl_ctx = _ssl.create_default_context()
        engine = create_engine(
            db_url, pool_pre_ping=True, pool_recycle=300,
            connect_args={"ssl_context": ssl_ctx},
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        DB_OK = True
        print("DB connected OK")
    except Exception as e:
        try:
            engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=300)
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            with engine.connect() as conn:
                conn.exec_driver_sql("SELECT 1")
            DB_OK = True
            DB_ERROR = None
            print("DB connected OK (fallback)")
        except Exception as e2:
            DB_ERROR = f"{type(e2).__name__}: {e2}"
            print("CRITICAL DB failed:", DB_ERROR)

Base = declarative_base()
app = Flask(__name__)
CORS(app)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    avatar = Column(String(32), default="snake_green")
    avatar_data = Column(Text, nullable=True)  # data:image/...;base64,... (small)
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
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    owner = relationship("User", back_populates="worlds")


class Friendship(Base):
    __tablename__ = "friendships"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    friend_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("user_id", "friend_id", name="uq_friendship"),)


class Block(Base):
    """ЧС — ban list per host (blocker bans blocked)"""
    __tablename__ = "blocks"
    id = Column(Integer, primary_key=True)
    blocker_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="uq_block"),)


class WorldBan(Base):
    """Ban from a specific world/host session (optional extra)"""
    __tablename__ = "world_bans"
    id = Column(Integer, primary_key=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("world_id", "user_id", name="uq_world_ban"),)


class WorldPlayer(Base):
    """Who is currently in a world (presence + reported RTT)"""
    __tablename__ = "world_players"
    id = Column(Integer, primary_key=True)
    world_id = Column(Integer, ForeignKey("worlds.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rtt_ms = Column(Integer, default=0)  # client-measured LAN-ish / local RTT
    is_host = Column(Boolean, default=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("world_id", "user_id", name="uq_world_player"),)


if engine is not None:
    try:
        Base.metadata.create_all(bind=engine)
        # soft migrate avatar column if missing
        try:
            with engine.connect() as conn:
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar VARCHAR(32) DEFAULT 'snake_green'"
                )
                conn.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_data TEXT"
                )
                conn.exec_driver_sql(
                    "ALTER TABLE worlds ADD COLUMN IF NOT EXISTS last_heartbeat TIMESTAMPTZ DEFAULT NOW()"
                )
                conn.commit()
        except Exception as mig_e:
            print("migrate note:", mig_e)
        print("Tables ensured")
    except Exception as e:
        print("create_all:", e)
        DB_ERROR = DB_ERROR or str(e)
        DB_OK = False


def get_db():
    if SessionLocal is None:
        raise RuntimeError(DB_ERROR or "Database not configured")
    return SessionLocal()


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
        if not hmac.compare_digest(_b64url(expected), sig_b):
            if not hmac.compare_digest(expected, _b64url_decode(sig_b)):
                return None
        data = json.loads(_b64url_decode(payload_b))
        if data.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            return None
        return data
    except Exception:
        return None


def user_to_dict(u, extra=None):
    d = {
        "id": u.id,
        "username": u.username,
        "avatar": u.avatar or "snake_green",
        "avatar_url": u.avatar_data if getattr(u, "avatar_data", None) else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }
    if extra:
        d.update(extra)
    return d


def world_to_dict(w):
    return {
        "id": w.id,
        "name": w.name,
        "description": w.description or "",
        "owner_id": w.owner_id,
        "owner_username": w.owner.username if w.owner else "?",
        "owner_avatar": (w.owner.avatar if w.owner else None) or "snake_green",
        "is_active": w.is_active,
        "player_count": w.player_count or 1,
        "max_players": w.max_players or 5,
        "host_ip": w.host_ip,
        "host_port": w.host_port,
        "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
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


def deactivate_stale_worlds(db):
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=HOST_TIMEOUT_SEC)
    db.query(World).filter(
        World.is_active == True,
        or_(World.last_heartbeat == None, World.last_heartbeat < cutoff),
    ).update({"is_active": False}, synchronize_session=False)
    db.commit()


@app.get("/")
def root():
    return {
        "name": "Multiplayer Snake",
        "version": "0.4.1",
        "description": "Лаунчер мультиплеера для Minecraft PE 1.1.5",
        "db_ok": DB_OK,
        "db_error": DB_ERROR,
    }


@app.get("/health")
def health():
    if not DB_OK or engine is None:
        return jsonify({"ok": False, "db": "down", "error": DB_ERROR or "no engine"}), 503
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return jsonify({"ok": True, "db": "up"})
    except Exception as e:
        return jsonify({"ok": False, "db": "down", "error": str(e)}), 503


@app.get("/avatars")
def list_avatars():
    return jsonify(AVATARS)


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
        user = User(username=username, password_hash=hash_password(password), avatar="snake_green")
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


@app.patch("/me")
@token_required
def update_me(user, db):
    data = request.get_json(silent=True) or {}
    try:
        if "avatar" in data:
            av = data["avatar"]
            if av not in AVATARS:
                return jsonify({"detail": "Неизвестный аватар"}), 400
            user.avatar = av
        if "avatar_data" in data:
            raw = data["avatar_data"]
            if raw is None or raw == "":
                user.avatar_data = None
            elif not isinstance(raw, str) or not raw.startswith("data:image/"):
                return jsonify({"detail": "Нужна картинка data:image/..."}), 400
            elif len(raw) > 400_000:  # ~300KB
                return jsonify({"detail": "Фото слишком большое (макс ~300KB)"}), 400
            else:
                user.avatar_data = raw
                user.avatar = "photo"
        db.commit()
        db.refresh(user)
        return jsonify(user_to_dict(user))
    finally:
        db.close()


@app.get("/users/search")
@token_required
def search_users(user, db):
    q = (request.args.get("q") or "").strip()
    if len(q) < 1:
        return jsonify([])
    try:
        rows = (
            db.query(User)
            .filter(User.username.ilike(f"%{q}%"), User.id != user.id)
            .limit(20)
            .all()
        )
        friend_ids = {
            f.friend_id
            for f in db.query(Friendship).filter(Friendship.user_id == user.id).all()
        }
        blocked_ids = {
            b.blocked_id
            for b in db.query(Block).filter(Block.blocker_id == user.id).all()
        }
        result = []
        for u in rows:
            result.append(user_to_dict(u, {
                "is_friend": u.id in friend_ids,
                "is_blocked": u.id in blocked_ids,
            }))
        return jsonify(result)
    finally:
        db.close()


# ---------- Friends ----------
@app.get("/friends")
@token_required
def list_friends(user, db):
    try:
        deactivate_stale_worlds(db)
        links = db.query(Friendship).filter(Friendship.user_id == user.id).all()
        result = []
        for link in links:
            friend = db.query(User).filter(User.id == link.friend_id).first()
            if not friend:
                continue
            hosting = (
                db.query(World)
                .filter(World.owner_id == friend.id, World.is_active == True)
                .first()
            )
            result.append(user_to_dict(friend, {
                "is_friend": True,
                "hosting": world_to_dict(hosting) if hosting else None,
            }))
        return jsonify(result)
    finally:
        db.close()



@app.get("/subscribers")
@token_required
def list_subscribers(user, db):
    """People who added me (I am in their friends list)."""
    try:
        links = db.query(Friendship).filter(Friendship.friend_id == user.id).all()
        result = []
        for link in links:
            sub = db.query(User).filter(User.id == link.user_id).first()
            if sub:
                result.append(user_to_dict(sub, {"is_subscriber": True}))
        return jsonify(result)
    finally:
        db.close()


@app.post("/friends/<int:friend_id>")
@token_required
def add_friend(user, db, friend_id):
    try:
        if friend_id == user.id:
            return jsonify({"detail": "Нельзя добавить себя"}), 400
        friend = db.query(User).filter(User.id == friend_id).first()
        if not friend:
            return jsonify({"detail": "Пользователь не найден"}), 404
        exists = db.query(Friendship).filter(
            Friendship.user_id == user.id, Friendship.friend_id == friend_id
        ).first()
        if exists:
            return jsonify({"detail": "Уже в друзьях", "user": user_to_dict(friend)})
        # One-way: I follow them; they see me as subscriber
        db.add(Friendship(user_id=user.id, friend_id=friend_id))
        db.commit()
        return jsonify({"ok": True, "user": user_to_dict(friend, {"is_friend": True})})
    finally:
        db.close()


@app.delete("/friends/<int:friend_id>")
@token_required
def remove_friend(user, db, friend_id):
    try:
        db.query(Friendship).filter(
            Friendship.user_id == user.id, Friendship.friend_id == friend_id
        ).delete(synchronize_session=False)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ---------- Blacklist (ЧС) ----------
@app.get("/blocks")
@token_required
def list_blocks(user, db):
    try:
        rows = db.query(Block).filter(Block.blocker_id == user.id).all()
        result = []
        for b in rows:
            u = db.query(User).filter(User.id == b.blocked_id).first()
            if u:
                result.append(user_to_dict(u, {"blocked_at": b.created_at.isoformat() if b.created_at else None}))
        return jsonify(result)
    finally:
        db.close()


@app.post("/blocks/<int:blocked_id>")
@token_required
def add_block(user, db, blocked_id):
    try:
        if blocked_id == user.id:
            return jsonify({"detail": "Нельзя забанить себя"}), 400
        target = db.query(User).filter(User.id == blocked_id).first()
        if not target:
            return jsonify({"detail": "Пользователь не найден"}), 404
        exists = db.query(Block).filter(
            Block.blocker_id == user.id, Block.blocked_id == blocked_id
        ).first()
        if not exists:
            db.add(Block(blocker_id=user.id, blocked_id=blocked_id))
        # remove friendship both ways
        db.query(Friendship).filter(
            or_(
                and_(Friendship.user_id == user.id, Friendship.friend_id == blocked_id),
                and_(Friendship.user_id == blocked_id, Friendship.friend_id == user.id),
            )
        ).delete(synchronize_session=False)
        db.commit()
        return jsonify({"ok": True, "user": user_to_dict(target)})
    finally:
        db.close()


@app.delete("/blocks/<int:blocked_id>")
@token_required
def remove_block(user, db, blocked_id):
    try:
        db.query(Block).filter(
            Block.blocker_id == user.id, Block.blocked_id == blocked_id
        ).delete(synchronize_session=False)
        db.commit()
        return jsonify({"ok": True})
    finally:
        db.close()


# ---------- Worlds / Host ----------
@app.get("/worlds")
def list_worlds():
    db = get_db()
    try:
        deactivate_stale_worlds(db)
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
        now = datetime.now(timezone.utc)
        # Strictly one active world per user: reuse existing active world
        world = (
            db.query(World)
            .filter(World.owner_id == user.id, World.is_active == True)
            .first()
        )
        if world:
            world.name = name
            world.description = description
            world.max_players = max_players
            world.player_count = 1
            world.last_heartbeat = now
            world.host_ip = data.get("host_ip")
            world.host_port = data.get("host_port")
        else:
            world = World(
                name=name,
                description=description,
                owner_id=user.id,
                max_players=max_players,
                player_count=1,
                is_active=True,
                last_heartbeat=now,
                host_ip=data.get("host_ip"),
                host_port=data.get("host_port"),
            )
            db.add(world)
        db.commit()
        db.refresh(world)
        _ = world.owner
        return jsonify(world_to_dict(world))
    finally:
        db.close()


@app.post("/worlds/<int:world_id>/heartbeat")
@token_required
def world_heartbeat(user, db, world_id):
    data = request.get_json(silent=True) or {}
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world:
            return jsonify({"detail": "Мир не найден"}), 404
        if world.owner_id != user.id:
            return jsonify({"detail": "Нет прав"}), 403
        world.is_active = True
        world.last_heartbeat = datetime.now(timezone.utc)
        if "player_count" in data:
            world.player_count = max(1, int(data["player_count"]))
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
        world.last_heartbeat = datetime.now(timezone.utc)
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
        db.query(WorldPlayer).filter(WorldPlayer.world_id == world_id).delete(synchronize_session=False)
        world.player_count = 0
        db.commit()
        return jsonify({"ok": True, "message": "Мир закрыт"})
    finally:
        db.close()


@app.post("/worlds/<int:world_id>/join-check")
@token_required
def join_check(user, db, world_id):
    """Check if user can join this world (not banned by host)."""
    try:
        world = db.query(World).filter(World.id == world_id, World.is_active == True).first()
        if not world:
            return jsonify({"detail": "Мир не найден или закрыт", "allowed": False}), 404
        blocked = db.query(Block).filter(
            Block.blocker_id == world.owner_id, Block.blocked_id == user.id
        ).first()
        if blocked:
            return jsonify({"detail": "Вы в ЧС у хоста", "allowed": False}), 403
        return jsonify({"allowed": True, "world": world_to_dict(world)})
    finally:
        db.close()


@app.post("/worlds/<int:world_id>/kick")
@token_required
def kick_player(user, db, world_id):
    """Informational kick — client should disconnect. Server records nothing permanent."""
    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id")
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world or world.owner_id != user.id:
            return jsonify({"detail": "Нет прав"}), 403
        if not target_id:
            return jsonify({"detail": "user_id обязателен"}), 400
        return jsonify({"ok": True, "action": "kick", "user_id": target_id})
    finally:
        db.close()


@app.post("/worlds/<int:world_id>/ban")
@token_required
def ban_from_world(user, db, world_id):
    """Ban player from host (adds to host's global block list)."""
    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id")
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world or world.owner_id != user.id:
            return jsonify({"detail": "Нет прав"}), 403
        if not target_id or target_id == user.id:
            return jsonify({"detail": "Некорректный user_id"}), 400
        target = db.query(User).filter(User.id == target_id).first()
        if not target:
            return jsonify({"detail": "Игрок не найден"}), 404
        exists = db.query(Block).filter(
            Block.blocker_id == user.id, Block.blocked_id == target_id
        ).first()
        if not exists:
            db.add(Block(blocker_id=user.id, blocked_id=target_id))
        db.query(Friendship).filter(
            or_(
                and_(Friendship.user_id == user.id, Friendship.friend_id == target_id),
                and_(Friendship.user_id == target_id, Friendship.friend_id == user.id),
            )
        ).delete(synchronize_session=False)
        db.commit()
        return jsonify({"ok": True, "action": "ban", "user": user_to_dict(target)})
    finally:
        db.close()




@app.post("/worlds/<int:world_id>/presence")
@token_required
def world_presence(user, db, world_id):
    """Join/leave/heartbeat presence in a world. Client sends rtt_ms (measured locally)."""
    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "heartbeat").lower()
    rtt_ms = int(data.get("rtt_ms") or 0)
    rtt_ms = max(0, min(5000, rtt_ms))
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world or not world.is_active:
            return jsonify({"detail": "Мир закрыт", "ok": False}), 404
        # blocked?
        blocked = db.query(Block).filter(
            Block.blocker_id == world.owner_id, Block.blocked_id == user.id
        ).first()
        if blocked and user.id != world.owner_id:
            return jsonify({"detail": "Вы в ЧС у хоста", "ok": False}), 403

        if action == "leave":
            db.query(WorldPlayer).filter(
                WorldPlayer.world_id == world_id, WorldPlayer.user_id == user.id
            ).delete(synchronize_session=False)
            # if host leaves — close world immediately
            if world.owner_id == user.id:
                world.is_active = False
                db.query(WorldPlayer).filter(WorldPlayer.world_id == world_id).delete(synchronize_session=False)
                world.player_count = 0
            else:
                cnt = db.query(WorldPlayer).filter(WorldPlayer.world_id == world_id).count()
                world.player_count = max(0, cnt)
            db.commit()
            return jsonify({"ok": True})

        now = datetime.now(timezone.utc)
        row = db.query(WorldPlayer).filter(
            WorldPlayer.world_id == world_id, WorldPlayer.user_id == user.id
        ).first()
        is_host = world.owner_id == user.id
        if not row:
            row = WorldPlayer(
                world_id=world_id, user_id=user.id,
                rtt_ms=rtt_ms, is_host=is_host, last_seen=now
            )
            db.add(row)
        else:
            row.rtt_ms = rtt_ms
            row.last_seen = now
            row.is_host = is_host
        if is_host:
            world.last_heartbeat = now
            world.is_active = True
        # prune stale players
        cutoff = now - timedelta(seconds=PLAYER_TIMEOUT_SEC)
        db.query(WorldPlayer).filter(
            WorldPlayer.world_id == world_id, WorldPlayer.last_seen < cutoff
        ).delete(synchronize_session=False)
        cnt = db.query(WorldPlayer).filter(WorldPlayer.world_id == world_id).count()
        world.player_count = max(1, cnt)
        db.commit()
        return jsonify({"ok": True, "player_count": world.player_count})
    finally:
        db.close()


@app.get("/worlds/<int:world_id>/players")
@token_required
def world_players(user, db, world_id):
    try:
        world = db.query(World).filter(World.id == world_id).first()
        if not world:
            return jsonify({"detail": "Мир не найден"}), 404
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=PLAYER_TIMEOUT_SEC)
        rows = (
            db.query(WorldPlayer)
            .filter(WorldPlayer.world_id == world_id, WorldPlayer.last_seen >= cutoff)
            .order_by(WorldPlayer.is_host.desc(), WorldPlayer.last_seen.desc())
            .all()
        )
        # ensure host is listed
        result = []
        seen = set()
        for row in rows:
            u = db.query(User).filter(User.id == row.user_id).first()
            if not u:
                continue
            seen.add(u.id)
            result.append(user_to_dict(u, {
                "rtt_ms": row.rtt_ms or 0,
                "is_host": bool(row.is_host),
                "last_seen": row.last_seen.isoformat() if row.last_seen else None,
            }))
        # if host missing from presence, still show
        if world.owner_id not in seen and world.owner:
            result.insert(0, user_to_dict(world.owner, {
                "rtt_ms": 0, "is_host": True, "last_seen": None,
            }))
        return jsonify({
            "world_id": world_id,
            "players": result,
            "is_owner": world.owner_id == user.id,
        })
    finally:
        db.close()


@app.errorhandler(Exception)
def handle_exception(e):
    import traceback
    traceback.print_exc()
    msg = str(e)
    if DB_ERROR and (
        "Database" in msg or "connection" in msg.lower()
        or "OperationalError" in type(e).__name__
        or "InterfaceError" in type(e).__name__
    ):
        return jsonify({"detail": f"База данных недоступна: {DB_ERROR}"}), 503
    return jsonify({"detail": msg or type(e).__name__}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print("Multiplayer Snake backend 0.4.0")
    print("http://0.0.0.0:%s" % port)
    app.run(host="0.0.0.0", port=port, debug=False)

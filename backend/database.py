from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config import get_settings

settings = get_settings()

db_url = settings.DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require", "")

# pg8000 — чистый Python, без компиляции (удобно для Termux)
if db_url.startswith("postgresql://") and "+pg8000" not in db_url and "+psycopg" not in db_url:
    db_url = db_url.replace("postgresql://", "postgresql+pg8000://", 1)

engine = create_engine(
    db_url,
    pool_pre_ping=True,
    pool_recycle=300,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

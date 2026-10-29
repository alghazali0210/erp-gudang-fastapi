import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Path absolut berdasarkan lokasi file ini, jadi database yang dipakai selalu sama
# walaupun server dijalankan dari folder yang berbeda.
# Bisa diganti lewat environment variable DATABASE_URL.
BASE_DIR = Path(__file__).resolve().parent
SQLALCHEMY_DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{BASE_DIR / 'sql_app.db'}"
)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # khusus SQLite
)


# SQLite secara bawaan tidak memberlakukan foreign key; aktifkan di setiap koneksi.
@event.listens_for(engine, "connect")
def aktifkan_foreign_key(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
"""Database connection and session management."""

from __future__ import annotations

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Lấy DATABASE_URL từ biến môi trường (Render cung cấp sẵn)
# Nếu không có DATABASE_URL, tạo từ các biến riêng lẻ
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    # Tạo connection string từ các biến riêng lẻ
    POSTGRES_USER = os.getenv('POSTGRES_USER')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
    POSTGRES_HOST = os.getenv('POSTGRES_HOST')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.getenv('POSTGRES_DB')
    
    # Render yêu cầu SSL, thêm ?sslmode=require vào connection string
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}?sslmode=require"
else:
    # Nếu DATABASE_URL đã có nhưng chưa có sslmode, thêm vào
    if 'sslmode' not in DATABASE_URL:
        separator = '&' if '?' in DATABASE_URL else '?'
        DATABASE_URL = f"{DATABASE_URL}{separator}sslmode=require"

# Normalize để dùng psycopg driver cho PostgreSQL
if DATABASE_URL.startswith('postgresql://'):
    DATABASE_URL = DATABASE_URL.replace('postgresql://', 'postgresql+psycopg://', 1)

# Tạo engine với pool_pre_ping để tự động reconnect khi connection bị mất
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # Tự động reconnect
    pool_size=10,        # Số lượng connections trong pool
    max_overflow=20,     # Số lượng connections tối đa có thể vượt quá pool_size
    connect_args={
        "sslmode": "require"  # Bắt buộc SSL cho Render
    } if 'render.com' in DATABASE_URL or os.getenv('POSTGRES_HOST', '').endswith('render.com') else {}
)

# Tạo session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class cho models
Base = declarative_base()

# Dependency để lấy database session
def get_db():
    """Dependency để inject database session vào FastAPI routes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

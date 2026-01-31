#!/usr/bin/env python3
"""
Start script cho Lumi CF service.
Chạy: python start.py
"""

from __future__ import annotations

import sys
import uvicorn
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from app.utils.init_db import init_db
    from app.utils.config import settings
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("   Make sure you've installed dependencies: pip install -r requirements.txt")
    sys.exit(1)


def parse_database_url(url: str, show_password: bool = False) -> dict[str, str]:
    """Parse DATABASE_URL và trả về thông tin connection (mask password mặc định)."""
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        
        # Password: mask hoặc hiển thị thật
        password = parsed.password or ""
        if show_password:
            display_password = password if password else "(empty)"
        else:
            # Mask password: chỉ hiển thị 2 ký tự đầu và 2 ký tự cuối
            if len(password) > 4:
                display_password = password[:2] + "*" * (len(password) - 4) + password[-2:]
            elif len(password) > 0:
                display_password = "*" * len(password)
            else:
                display_password = "(empty)"
        
        return {
            "scheme": parsed.scheme,
            "user": parsed.username or "(none)",
            "password": display_password,
            "password_raw": password,  # Lưu password thật để dùng khi cần
            "host": parsed.hostname or "(none)",
            "port": str(parsed.port or 5432),
            "database": (parsed.path or "").lstrip("/") or "(none)",
            "query": parsed.query or "(none)",
            "full_masked": f"{parsed.scheme}://{parsed.username or ''}:{display_password}@{parsed.hostname or ''}:{parsed.port or 5432}{parsed.path or ''}{'?' + parsed.query if parsed.query else ''}",
        }
    except Exception as e:
        return {"error": str(e), "raw_url": url[:50] + "..." if len(url) > 50 else url}


def check_database_connection() -> bool:
    """Kiểm tra kết nối database."""
    try:
        from sqlalchemy import text
        from app.utils.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Database connection failed: {error_msg}")
        
        # Hướng dẫn xử lý lỗi phổ biến
        if "password authentication failed" in error_msg.lower():
            print()
            print("💡 Troubleshooting:")
            print("   1. Kiểm tra password trong .env có đúng không")
            print("   2. Nếu password có ký tự đặc biệt (@, #, %, &, ...), cần URL encode:")
            print("      Ví dụ: password 'p@ss#123' → 'p%40ss%23123'")
            print("   3. Kiểm tra user có quyền truy cập database không")
            print("   4. Kiểm tra IP có được whitelist trên database server không")
        elif "could not connect" in error_msg.lower() or "connection refused" in error_msg.lower():
            print()
            print("💡 Troubleshooting:")
            print("   1. Kiểm tra host/port trong DATABASE_URL có đúng không")
            print("   2. Kiểm tra database server có đang chạy không")
            print("   3. Kiểm tra firewall/network có block connection không")
        
        return False


def main() -> None:
    """Khởi động CF service."""
    print("=" * 60)
    print("🚀 Starting Lumi CF Service")
    print("=" * 60)
    
    # Hiển thị thông tin config
    # Check nếu có DEBUG=1 trong env thì show password thật
    import os
    debug_mode = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")
    db_info = parse_database_url(settings.DATABASE_URL, show_password=debug_mode)
    
    print(f"📊 Database connection info:")
    print(f"   Scheme: {db_info.get('scheme', 'unknown')}")
    print(f"   User: {db_info.get('user', 'unknown')}")
    if debug_mode:
        print(f"   Password: {db_info.get('password_raw', 'unknown')} ⚠️  (DEBUG MODE)")
    else:
        print(f"   Password: {db_info.get('password', 'unknown')} (masked)")
        print(f"   💡 Set DEBUG=1 to see actual password")
    print(f"   Host: {db_info.get('host', 'unknown')}")
    print(f"   Port: {db_info.get('port', 'unknown')}")
    print(f"   Database: {db_info.get('database', 'unknown')}")
    if db_info.get('query') and db_info['query'] != "(none)":
        print(f"   Query params: {db_info.get('query', '')}")
    print(f"   Full URL (masked): {db_info.get('full_masked', 'N/A')}")
    print()
    print(f"📦 Model path: {settings.MODEL_PATH}")
    print(f"⚙️  Default K: {settings.DEFAULT_K}, Max K: {settings.MAX_K}")
    print()
    
    # Kiểm tra kết nối database
    print("🔍 Checking database connection...")
    db_ok = check_database_connection()
    if not db_ok:
        print()
        print("⚠️  Warning: Cannot connect to database")
        print("   Service will start but may fail on first request")
        print("   Bạn có muốn tiếp tục? (y/n): ", end="")
        try:
            response = input().strip().lower()
            if response != 'y':
                print("👋 Exiting...")
                sys.exit(1)
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Exiting...")
            sys.exit(1)
        print()
    else:
        print("✅ Database connection OK")
        print()
    
    # Init DB tables nếu chưa có
    print("🔧 Initializing database tables...")
    try:
        init_db()
        print("✅ Database tables ready")
    except Exception as e:
        print(f"⚠️  Warning: Could not init DB tables: {e}")
        print("   (Tables may already exist or there's a connection issue)")
        print("   Service will continue anyway...")
    print()
    
    # Start uvicorn server
    print("=" * 60)
    print("🌐 Starting API server...")
    print("=" * 60)
    print(f"📍 Server URL: http://0.0.0.0:8000")
    print(f"📖 API Docs: http://127.0.0.1:8000/docs")
    print(f"📋 ReDoc: http://127.0.0.1:8000/redoc")
    print(f"💚 Health: http://127.0.0.1:8000/health")
    print()
    print("💡 Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    try:
        uvicorn.run(
            "app.utils.main:app",
            host="0.0.0.0",
            port=8000,
            reload=True,  # auto-reload khi code thay đổi (dev mode)
            log_level="info",
            access_log=True,
        )
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

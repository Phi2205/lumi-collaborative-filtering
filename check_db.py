
import asyncio
from sqlalchemy import text
from app.utils.database import engine

async def check_schema():
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_profile_features'"))
        columns = [row[0] for row in result.fetchall()]
        print(f"Columns in user_profile_features: {columns}")

if __name__ == "__main__":
    import asyncio
    try:
        # Check if engine is async or sync
        from sqlalchemy.ext.asyncio import AsyncEngine
        if isinstance(engine, AsyncEngine):
            asyncio.run(check_schema())
        else:
            with engine.connect() as conn:
                result = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'user_profile_features'"))
                columns = [row[0] for row in result.fetchall()]
                print(f"Columns in user_profile_features: {columns}")
    except Exception as e:
        print(f"Error: {e}")

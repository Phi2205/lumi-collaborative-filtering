
from sqlalchemy import text
from app.utils.database import engine

def fix_db():
    with engine.connect() as conn:
        print("Adding unique_reels_interacted to user_profile_features...")
        try:
            conn.execute(text("ALTER TABLE user_profile_features ADD COLUMN IF NOT EXISTS unique_reels_interacted INTEGER NOT NULL DEFAULT 0"))
            conn.commit()
            print("Successfully added unique_reels_interacted.")
        except Exception as e:
            print(f"Error adding column: {e}")

        # Let's also make sure other tables exist
        from app import models
        from app.utils.database import Base
        print("Creating any other missing tables...")
        Base.metadata.create_all(bind=engine)
        print("Migration complete.")

if __name__ == "__main__":
    from sqlalchemy.ext.asyncio import AsyncEngine
    if isinstance(engine, AsyncEngine):
        import asyncio
        async def fix_async():
            async with engine.begin() as conn:
                print("Adding unique_reels_interacted to user_profile_features...")
                await conn.execute(text("ALTER TABLE user_profile_features ADD COLUMN IF NOT EXISTS unique_reels_interacted INTEGER NOT NULL DEFAULT 0"))
                print("Successfully added unique_reels_interacted.")
            
            async with engine.begin() as conn:
                from app import models
                from app.utils.database import Base
                print("Creating any other missing tables...")
                await conn.run_sync(Base.metadata.create_all)
                print("Migration complete.")
        asyncio.run(fix_async())
    else:
        fix_db()

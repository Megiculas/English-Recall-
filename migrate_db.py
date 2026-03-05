import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from config import settings

async def run_migration():
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if "?" in db_url:
        db_url = db_url.split("?")[0]
        
    connect_args = {}
    if "neon.tech" in db_url:
        connect_args["ssl"] = "require"
        
    engine = create_async_engine(db_url, connect_args=connect_args)
    
    try:
        async with engine.begin() as conn:
            print("Виконую міграцію бази даних: додавання поля is_waiting_for_review...")
            await conn.execute(text("ALTER TABLE words ADD COLUMN IF NOT EXISTS is_waiting_for_review BOOLEAN DEFAULT FALSE;"))
            print("Міграція успішна!")
    except Exception as e:
        print(f"Помилка міграції: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(run_migration())

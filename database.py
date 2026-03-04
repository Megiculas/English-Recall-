from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings
from models import Base

# Створюємо асинхронний рушій БД
# Важливо: URL має починатися з postgresql+asyncpg://
# asyncpg не підтримує параметр sslmode=require у рядку підключення, тому ми його видаляємо
clean_db_url = settings.DATABASE_URL.replace("?sslmode=require", "")
engine = create_async_engine(clean_db_url, echo=False)

# Фабрика сесій
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def init_db():
    """Створює таблиці в БД, якщо їх ще немає. 
    (В продакшені краще юзати Alembic, але для MVP підійде це)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings
from models import Base

db_url = settings.DATABASE_URL

# Автоматично змінюємо драйвер на asyncpg, якщо юзер просто скопіював посилання
if db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# Видаляємо параметри на зразок ?sslmode=require&channel_binding=require, бо asyncpg їх не підтримує таким чином
if "?" in db_url:
    db_url = db_url.split("?")[0]

connect_args = {}
# Neon.tech вимагає SSL-з'єднання
if "neon.tech" in db_url:
    connect_args["ssl"] = "require"

engine = create_async_engine(db_url, connect_args=connect_args, echo=False)

# Фабрика сесій
AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

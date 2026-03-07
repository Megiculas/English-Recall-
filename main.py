import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from database import engine
from scheduler import start_scheduler

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація бота та диспетчера
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Мідлвар для перевірки ALLOWED_USER_ID (повідомлення)
@dp.message.outer_middleware()
async def check_user_middleware(handler, event: types.Message, data: dict):
    if event.from_user.id != settings.ALLOWED_USER_ID:
        await event.answer("Вибачте, цей бот є приватним.")
        return
    return await handler(event, data)

# Мідлвар для перевірки ALLOWED_USER_ID (колбеки)
@dp.callback_query.outer_middleware()
async def check_callback_user_middleware(handler, event: types.CallbackQuery, data: dict):
    if event.from_user.id != settings.ALLOWED_USER_ID:
        await event.answer("Вибачте, цей бот є приватним.")
        return
    return await handler(event, data)

# Додаємо роутер зі словами
from routers import words
dp.include_router(words.router)

from aiohttp import web
import os

async def dummy_handler(request):
    return web.Response(text="Bot is running!")

async def api_add_word(request):
    """API ендпоінт для додавання слів з Chrome-розширення."""
    try:
        data = await request.json()
    except Exception:
        return web.json_response({"error": "Invalid JSON"}, status=400)

    word = data.get("word", "").strip()
    api_key = data.get("api_key", "")

    # Перевірка секретного ключа
    if not settings.API_SECRET or api_key != settings.API_SECRET:
        return web.json_response({"error": "Unauthorized"}, status=401)

    if not word:
        return web.json_response({"error": "No word provided"}, status=400)

    # Використовуємо спільну логіку обробки слова
    from routers.words import process_new_word
    result = await process_new_word(
        user_id=settings.ALLOWED_USER_ID,
        input_text=word,
        bot=bot,
        source="api"
    )

    return web.json_response({
        "status": result["status"],
        "word": word,
        "translation": result.get("card_data", {}).get("translation", ""),
        "already_exists": result.get("already_exists", False),
    })

from alembic.config import Config
from alembic import command
from alembic.migration import MigrationContext
from sqlalchemy import inspect

async def run_migrations():
    """Запускає Alembic міграції при старті бота"""
    def run_upgrade(connection, cfg):
        cfg.attributes["connection"] = connection
        
        # Перевіряємо наявність таблиць для уникнення DuplicateTableError
        inspector = inspect(connection)
        tables = inspector.get_table_names()
        
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()
        
        if current_rev is None and "users" in tables:
            logger.info("База даних вже містить таблиці. Виконуємо alembic stamp head...")
            command.stamp(cfg, "head")
            
        command.upgrade(cfg, "head")
        
    async with engine.begin() as conn:
        alembic_cfg = Config("alembic.ini")
        await conn.run_sync(run_upgrade, alembic_cfg)

async def main():
    logger.info("Виконання міграції бази даних (Alembic)...")
    await run_migrations()
    
    logger.info("Запуск планувальника...")
    start_scheduler(bot)
    
    logger.info("Запуск бота та веб-сервера...")
    # Налаштування dummy сервера для Render (щоб не падав deploy)
    app = web.Application()
    app.router.add_get('/', dummy_handler)
    app.router.add_post('/api/word', api_add_word)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Веб-сервер запущений на порту {port}")
    
    # Запускаємо polling бота (це блокувальний виклик, тому він має бути останнім)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")

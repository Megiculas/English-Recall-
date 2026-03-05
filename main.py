import asyncio
import logging
from aiogram import Bot, Dispatcher, types
import json
from aiogram.filters import CommandStart
from sqlalchemy import select
from config import settings
from database import AsyncSessionLocal, engine
from models import Word
from llm import generate_word_card

# Налаштування логування
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ініціалізація бота та диспетчера
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()

# Мідлвар для перевірки ALLOWED_USER_ID
@dp.message.outer_middleware()
async def check_user_middleware(handler, event: types.Message, data: dict):
    if event.from_user.id != settings.ALLOWED_USER_ID:
        await event.answer("Вибачте, цей бот є приватним.")
        return
    return await handler(event, data)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привіт! Я твій персональний бот для вивчення англійської. 🇬🇧\n"
        "Просто надішли мені незнайоме слово або фразу, і я додам його до твоєї бази "
        "з прикладами, транскрипцією та запущу інтервальне повторення!"
    )

@dp.message()
async def add_word_handler(message: types.Message):
    user_id = message.from_user.id
    input_text = message.text.strip()
    
    if not input_text:
        return
        
    # Балістична перевірка: чи вже є це слово
    async with AsyncSessionLocal() as session:
        stmt = select(Word).where(
            Word.user_id == user_id,
            Word.word.ilike(input_text.lower())
        )
        result = await session.execute(stmt)
        existing_word = result.scalars().first()
        
        if existing_word:
            await message.reply(f"Слово або фраза '{input_text}' вже є у твоїй базі (рівень {existing_word.level}).")
            return
            
    processing_msg = await message.reply("⏳ Аналізую слово та генерую картку...")
    
    # Генерація картки через LLM
    llm_response_json = await generate_word_card(input_text)
    
    try:
        card_data = json.loads(llm_response_json)
    except json.JSONDecodeError:
        card_data = {
            "translation": "Помилка парсингу",
            "transcription": "[-]",
            "example": "-",
            "synonyms": "-",
            "tags": ""
        }
        
    # Збереження в базу
    async with AsyncSessionLocal() as session:
        new_word = Word(
            user_id=user_id,
            word=input_text.lower(),
            context_given=input_text,
            llm_response=json.dumps(card_data, ensure_ascii=False)
        )
        session.add(new_word)
        await session.commit()
        
    # Форматування та відправка відповіді
    response_text = (
        f"🔤 <b>{input_text.upper()}</b>\n"
        f"───────────────\n"
        f"🇺🇦 {card_data.get('translation', '')}\n"
        f"🗣 {card_data.get('transcription', '')}\n"
        f"📖 <i>{card_data.get('example', '')}</i>\n"
        f"🔗 Синоніми: {card_data.get('synonyms', '')}\n"
        f"⚡️ {card_data.get('tags', '')}"
    )
    
    await processing_msg.edit_text(response_text, parse_mode="HTML")

from aiogram import F
from scheduler import start_scheduler, REVIEW_INTERVALS
from datetime import datetime, timezone

@dp.callback_query(F.data.startswith("review_"))
async def process_review_callback(callback: types.CallbackQuery):
    action, word_id_str = callback.data.split("_")[1:3]
    word_id = int(word_id_str)
    
    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)
        
        if not word:
            await callback.answer("Слово не знайдено.")
            return
            
        now = datetime.now(timezone.utc)
        
        try:
            card_data = json.loads(word.llm_response)
        except:
            card_data = {}
            
        if action == "yes":
            word.level += 1
            if word.level >= len(REVIEW_INTERVALS):
                word.is_learned = True
                msg_text = f"🎉 Ти повністю вивчив слово <b>{word.word.upper()}</b>!\n\nПереклад: {card_data.get('translation', '')}"
            else:
                word.next_review = now + REVIEW_INTERVALS[word.level]
                msg_text = f"✅ Чудово! Наступне повторення через {REVIEW_INTERVALS[word.level]}.\n\n<b>{word.word.upper()}</b> — {card_data.get('translation', '')}"
        else:
            word.level = 0
            word.next_review = now + REVIEW_INTERVALS[0]
            msg_text = f"🔄 Нічого страшного, повторимо ще раз через {REVIEW_INTERVALS[0]}.\n\n<b>{word.word.upper()}</b> — {card_data.get('translation', '')}\nПриклад: <i>{card_data.get('example', '')}</i>"
            
        # Знімаємо прапорець очікування
        word.is_waiting_for_review = False
        session.add(word)
        await session.commit()
        
    await callback.message.edit_text(msg_text, parse_mode="HTML")
    await callback.answer()

from aiohttp import web
import os

async def dummy_handler(request):
    return web.Response(text="Bot is running!")

from alembic.config import Config
from alembic import command

async def run_migrations():
    """Запускає Alembic міграції при старті бота"""
    def run_upgrade(connection, cfg):
        cfg.attributes["connection"] = connection
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
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Запускаємо polling бота
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот зупинений.")


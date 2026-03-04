import asyncio
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from database import AsyncSessionLocal
from models import Word
from config import settings

# Інтервали за Еббінгаузом (в годинах/днях)
REVIEW_INTERVALS = {
    0: timedelta(hours=4),
    1: timedelta(days=1),
    2: timedelta(days=3),
    3: timedelta(days=7),
    4: timedelta(days=14),
    5: timedelta(days=30),
}

async def check_words_for_review(bot):
    """Фонова задача для перевірки слів, які настав час повторювати."""
    now = datetime.now(timezone.utc)
    
    async with AsyncSessionLocal() as session:
        # Знаходимо слова, які час повторити і які ще не вивчені повністю
        stmt = select(Word).where(
            Word.next_review <= now,
            Word.is_learned == False
        )
        result = await session.execute(stmt)
        words_to_review = result.scalars().all()
        
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        
        for word in words_to_review:
            # Створюємо клавіатуру для тесту
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Пам'ятаю", callback_data=f"review_yes_{word.id}"),
                    InlineKeyboardButton(text="❌ Забув", callback_data=f"review_no_{word.id}")
                ]
            ])
            
            await bot.send_message(
                chat_id=word.user_id,
                text=f"🕐 Час повторити слово: <b>{word.word.upper()}</b>\n"
                     f"Ти пам'ятаєш його переклад та значення?",
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            
        if words_to_review:
            await session.commit()

def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    # Перевіряємо кожні 5 хвилин
    scheduler.add_job(check_words_for_review, 'interval', minutes=5, args=[bot])
    scheduler.start()
    return scheduler

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
    
    # 1. Скидання завислих карток
    # (якщо користувач не відповів протягом 24 годин — скидаємо прапорець, щоб нагадати знову)
    async with AsyncSessionLocal() as session:
        stale_threshold = now - timedelta(hours=24)
        stmt_stale = select(Word).where(
            Word.is_waiting_for_review == True,
            Word.next_review <= stale_threshold
        )
        stale_result = await session.execute(stmt_stale)
        stale_words = stale_result.scalars().all()
        
        for word in stale_words:
            word.is_waiting_for_review = False
            session.add(word)
            
        if stale_words:
            await session.commit()
            
    # "Тихі години": не надсилати повідомлення з 23:00 до 08:00 за київським часом (UTC+2 / UTC+3)
    # Зробимо просту перевірку по UTC: 23:00 Київ = 21:00 UTC (або 20:00 влітку), 08:00 = 06:00 UTC.
    # Для простоти припускаємо ніч з 21:00 по 06:00 UTC.
    current_utc_hour = now.hour
    if current_utc_hour >= 21 or current_utc_hour < 6:
        return # Пропускаємо перевірку під час "тихих годин"

    async with AsyncSessionLocal() as session:
        # 2. Знаходимо нові слова для перевірки
        stmt = select(Word).where(
            Word.next_review <= now,
            Word.is_learned == False,
            Word.is_waiting_for_review == False
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
            
            # Ставимо прапорець, щоб на наступній ітерації через 5 хв не відправити знову
            word.is_waiting_for_review = True
            session.add(word)
            
        if words_to_review:
            await session.commit()

def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    # Перевіряємо кожні 5 хвилин
    scheduler.add_job(check_words_for_review, 'interval', minutes=5, args=[bot])
    scheduler.start()
    return scheduler

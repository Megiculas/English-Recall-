import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from database import AsyncSessionLocal
from models import Word
from config import settings

logger = logging.getLogger(__name__)

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
    try:
        now = datetime.now(timezone.utc)
        
        # 1. Скидання завислих карток (24 год без відповіді)
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
                logger.info(f"Скинуто {len(stale_words)} завислих карток")
                await session.commit()
                
        # "Тихі години": 21:00 - 06:00 UTC (приблизно 23:00 - 08:00 Київ)
        current_utc_hour = now.hour
        if current_utc_hour >= 21 or current_utc_hour < 6:
            return

        async with AsyncSessionLocal() as session:
            stmt = select(Word).where(
                Word.next_review <= now,
                Word.is_learned == False,
                Word.is_waiting_for_review == False
            )
            result = await session.execute(stmt)
            words_to_review = result.scalars().all()
            
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            
            for word in words_to_review:
                try:
                    keyboard = InlineKeyboardMarkup(inline_keyboard=[
                        [
                            InlineKeyboardButton(text="✅ Пам'ятаю", callback_data=f"review_yes_{word.id}"),
                            InlineKeyboardButton(text="❌ Забув", callback_data=f"review_no_{word.id}")
                        ]
                    ])
                    
                    await bot.send_message(
                        chat_id=word.user_id,
                        text=f"🕐 Час повторити: <b>{word.word.upper()}</b>\n"
                             f"Ти пам'ятаєш його переклад?",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    
                    word.is_waiting_for_review = True
                    session.add(word)
                except Exception as e:
                    logger.error(f"Помилка відправки review для слова {word.word} (id={word.id}): {e}")
                    continue
                
            if words_to_review:
                await session.commit()
    except Exception as e:
        logger.error(f"Помилка в check_words_for_review: {e}")

def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_words_for_review, 'interval', minutes=5, args=[bot])
    scheduler.start()
    logger.info("Планувальник запущений (інтервал: 5 хв)")
    return scheduler

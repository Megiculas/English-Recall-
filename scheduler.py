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
    """Фонова задача для індивідуальних нагадувань (тільки для ACTIVE слотів)."""
    try:
        now = datetime.now(timezone.utc)
        
        async with AsyncSessionLocal() as session:
            # 1. Скидання завислих карток
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
                
            # 2. Вибірка тільки ACTIVE слів
            stmt = select(Word).where(
                Word.status == "active",
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
                        text=f"🔥 FOCUS: <b>{word.word.upper()}</b>\n"
                             f"Ти пам'ятаєш переклад?",
                        reply_markup=keyboard,
                        parse_mode="HTML"
                    )
                    word.is_waiting_for_review = True
                    session.add(word)
                except Exception as e:
                    logger.error(f"Помилка відправки review для {word.word}: {e}")
                    continue
            if words_to_review:
                await session.commit()
    except Exception as e:
        logger.error(f"Помилка в check_words_for_review: {e}")

async def process_batch_reviews(bot):
    """Щоденна розсилка для BACKLOG слів (о 19:00)."""
    try:
        now = datetime.now(timezone.utc)
        async with AsyncSessionLocal() as session:
            # Знайти всіх користувачів
            users_stmt = select(User)
            users_res = await session.execute(users_stmt)
            users = users_res.scalars().all()
            
            for user in users:
                # Знайти слова в беклозі для цього користувача
                stmt = select(Word).where(
                    Word.user_id == user.id,
                    Word.status == "backlog",
                    Word.next_review <= now,
                    Word.is_learned == False
                ).limit(20) # Не більше 20 за раз для зручності
                
                res = await session.execute(stmt)
                words = res.scalars().all()
                
                if not words: continue
                
                text = "📚 <b>Вечірній Backlog-повтор</b>\n"
                text += "Час освіжити ці старіші слова:\n\n"
                for w in words:
                    text += f"• <b>{w.word.upper()}</b>\n"
                
                text += "\nНатисни /practice щоб повторити їх зараз!"
                
                try:
                    await bot.send_message(chat_id=user.id, text=text, parse_mode="HTML")
                    # Для беклогу ми просто нагадуємо, не ставимо is_waiting_for_review
                except Exception: continue
                
    except Exception as e:
        logger.error(f"Помилка в process_batch_reviews: {e}")

def start_scheduler(bot):
    scheduler = AsyncIOScheduler()
    # Кожні 5 хвилин для активних слотів
    scheduler.add_job(check_words_for_review, 'interval', minutes=5, args=[bot])
    # Щодня о 19:00 для беклогу
    scheduler.add_job(process_batch_reviews, 'cron', hour=19, minute=0, args=[bot])
    
    scheduler.start()
    logger.info("Планувальник (Funnel) запущений")
    return scheduler

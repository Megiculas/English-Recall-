from datetime import datetime, timezone
from sqlalchemy import select, func
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from models import Word, User

async def update_user_activity(session, user) -> bool:
    """Оновлює активність користувача (streak)."""
    now = datetime.now(timezone.utc)
    updated = False
    
    if user.last_activity is None:
        user.current_streak = 1
        user.max_streak = 1
        user.last_activity = now
        updated = True
    else:
        last_date = user.last_activity.date()
        today = now.date()
        delta_days = (today - last_date).days
        
        if delta_days == 1:
            user.current_streak += 1
            if user.current_streak > user.max_streak:
                user.max_streak = user.current_streak
            user.last_activity = now
            updated = True
        elif delta_days > 1:
            user.current_streak = 1
            user.last_activity = now
            updated = True
            
    return updated

async def get_active_count(session, user_id: int) -> int:
    """Повертає кількість слів у статусі 'active' для користувача."""
    return await session.scalar(
        select(func.count(Word.id)).where(Word.user_id == user_id, Word.status == "active")
    ) or 0

async def promote_next_word(session, user_id: int):
    """Шукає найстаріше слово в Inbox і переводить його в Active, якщо є вільні слоти."""
    user = await session.get(User, user_id)
    if not user: return

    active_count = await get_active_count(session, user_id)
    if active_count < user.active_slots_limit:
        stmt = (
            select(Word)
            .where(Word.user_id == user_id, Word.status == "inbox")
            .order_by(Word.added_at.asc())
            .limit(1)
        )
        res = await session.execute(stmt)
        word = res.scalars().first()
        if word:
            word.status = "active"
            word.next_review = datetime.now(timezone.utc) # Почати навчання відразу
            session.add(word)
            return word
    return None

async def graduate_word_if_needed(session, word: Word):
    """Переводить слово в Backlog, якщо воно досягло Level 2."""
    if word.status == "active" and word.level >= 2:
        word.status = "backlog"
        session.add(word)
        # Оскільки звільнився слот - спробуємо заповнити його
        await promote_next_word(session, word.user_id)
        return True
    return False

def get_pagination_keyboard(current_page: int, total_pages: int, prefix: str = "list") -> InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації."""
    buttons = []
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_page_{current_page - 1}"))
    buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="ignore"))
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_page_{current_page + 1}"))
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

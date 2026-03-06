from datetime import datetime, timezone
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

async def update_user_activity(session, user) -> bool:
    """
    Оновлює активність користувача (streak).
    Повертає True, якщо стрік збільшився (новий день).
    """
    now = datetime.now(timezone.utc)
    updated = False
    
    if user.last_activity is None:
        user.current_streak = 1
        user.max_streak = 1
        user.last_activity = now
        updated = True
    else:
        # Перевіряємо різницю в датах
        last_date = user.last_activity.date()
        today = now.date()
        delta_days = (today - last_date).days
        
        if delta_days == 1:
            # Наступний день - збільшуємо стрік
            user.current_streak += 1
            if user.current_streak > user.max_streak:
                user.max_streak = user.current_streak
            user.last_activity = now
            updated = True
        elif delta_days > 1:
            # Стрік втрачено
            user.current_streak = 1
            user.last_activity = now
            updated = True
        elif delta_days == 0:
            # Той самий день - нічого не міняємо
            # Можна оновити last_activity, щоб знати час останньої події,
            # але для логіки стріків це не є обов'язковим.
            pass
            
    return updated

def get_pagination_keyboard(current_page: int, total_pages: int, prefix: str = "list") -> InlineKeyboardMarkup:
    """Генерує клавіатуру для пагінації."""
    buttons = []
    
    if current_page > 1:
        buttons.append(InlineKeyboardButton(text="⬅️", callback_data=f"{prefix}_page_{current_page - 1}"))
        
    buttons.append(InlineKeyboardButton(text=f"{current_page}/{total_pages}", callback_data="ignore"))
    
    if current_page < total_pages:
        buttons.append(InlineKeyboardButton(text="➡️", callback_data=f"{prefix}_page_{current_page + 1}"))
        
    return InlineKeyboardMarkup(inline_keyboard=[buttons])

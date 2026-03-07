import json
import math
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func
from database import AsyncSessionLocal
from models import Word, User
from llm import generate_word_card
from scheduler import REVIEW_INTERVALS
from states import EditTranslationState
from utils import update_user_activity, get_pagination_keyboard

logger = logging.getLogger(__name__)
router = Router()


# ────────────────────────────────────────────
#  Допоміжна функція для отримання card_data
# ────────────────────────────────────────────
def get_card_data(word: Word) -> dict:
    """Безпечно витягує card_data з llm_response (JSONB або str)."""
    try:
        if isinstance(word.llm_response, dict):
            return word.llm_response
        elif isinstance(word.llm_response, str):
            return json.loads(word.llm_response)
    except Exception:
        pass
    return {}


def format_card_text(input_text: str, card_data: dict) -> str:
    """Форматує текст картки для відправки."""
    return (
        f"🔤 <b>{input_text.upper()}</b>\n"
        f"───────────────\n"
        f"🇺🇦 {card_data.get('translation', '')}\n"
        f"🗣 {card_data.get('transcription', '')}\n"
        f"📖 <i>{card_data.get('example', '')}</i>\n"
        f"🔗 Синоніми: {card_data.get('synonyms', '')}\n"
        f"⚡️ {card_data.get('tags', '')}"
    )


async def process_new_word(user_id: int, input_text: str, bot=None, source: str = "telegram") -> dict:
    """
    Спільна логіка обробки нового слова.
    Повертає dict: {status, card_data, word_id, response_text, already_exists}
    """
    # Перевірка на дублікат
    async with AsyncSessionLocal() as session:
        stmt = select(Word).where(
            Word.user_id == user_id,
            Word.word.ilike(input_text.lower())
        )
        result = await session.execute(stmt)
        existing_word = result.scalars().first()

        if existing_word:
            card = get_card_data(existing_word)
            return {
                "status": "exists",
                "card_data": card,
                "word_id": existing_word.id,
                "already_exists": True,
            }

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
        user = await session.get(User, user_id)
        if not user:
            user = User(id=user_id)
            session.add(user)

        await update_user_activity(session, user)

        now = datetime.now(timezone.utc)
        new_word = Word(
            user_id=user_id,
            word=input_text.lower(),
            context_given=input_text,
            llm_response=card_data,
            next_review=now + REVIEW_INTERVALS[0]
        )
        session.add(new_word)
        await session.commit()
        word_id = new_word.id

    response_text = format_card_text(input_text, card_data)

    # Якщо це з API (не з Telegram), відправляємо повідомлення в Telegram
    if source == "api" and bot:
        from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_trans_{word_id}"),
                InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete_word_{word_id}")
            ]
        ])
        source_label = "\n\n🌐 <i>Додано з Chrome-розширення</i>"
        await bot.send_message(
            chat_id=user_id,
            text=response_text + source_label,
            parse_mode="HTML",
            reply_markup=keyboard
        )

    return {
        "status": "ok",
        "card_data": card_data,
        "word_id": word_id,
        "response_text": response_text,
        "already_exists": False,
    }


# ────────────────────────────────────────────
#  /start
# ────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(message: types.Message):
    async with AsyncSessionLocal() as session:
        user = await session.get(User, message.from_user.id)
        if not user:
            user = User(id=message.from_user.id)
            session.add(user)
            await session.commit()

    await message.answer(
        "Привіт! Я твій персональний бот для вивчення англійської. 🇬🇧\n"
        "Просто надішли мені незнайоме слово або фразу, і я додам його до твоєї бази "
        "з прикладами, транскрипцією та запущу інтервальне повторення!\n\n"
        "📌 <b>Корисні команди:</b>\n"
        "/stats — Твоя статистика та стрік\n"
        "/list — Список усіх слів\n"
        "/practice — Миттєве тренування\n"
        "/delete &lt;слово&gt; — Видалити слово",
        parse_mode="HTML"
    )


# ────────────────────────────────────────────
#  /stats
# ────────────────────────────────────────────
@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)

        total_words = await session.scalar(
            select(func.count(Word.id)).where(Word.user_id == user_id)
        ) or 0

        learned_words = await session.scalar(
            select(func.count(Word.id)).where(Word.user_id == user_id, Word.is_learned == True)
        ) or 0

        in_progress = total_words - learned_words

        now = datetime.now(timezone.utc)
        due_now = await session.scalar(
            select(func.count(Word.id)).where(
                Word.user_id == user_id,
                Word.is_learned == False,
                Word.next_review <= now
            )
        ) or 0

        streak = user.current_streak if user else 0
        max_streak = user.max_streak if user else 0

    # Прогрес бар
    if total_words > 0:
        pct = int(learned_words / total_words * 100)
        filled = pct // 10
        bar = "█" * filled + "░" * (10 - filled)
        progress_line = f"📈 Прогрес: [{bar}] {pct}%"
    else:
        progress_line = "📈 Прогрес: додай перше слово!"

    stats_text = (
        f"📊 <b>Твоя статистика</b>\n"
        f"───────────────\n"
        f"📝 Всього слів: <b>{total_words}</b>\n"
        f"🎓 Вивчено: <b>{learned_words}</b>\n"
        f"📚 В процесі: <b>{in_progress}</b>\n"
        f"⏰ Очікують повторення зараз: <b>{due_now}</b>\n\n"
        f"{progress_line}\n\n"
        f"🔥 Стрік: <b>{streak} днів</b>  |  🏆 Рекорд: <b>{max_streak} днів</b>"
    )
    await message.answer(stats_text, parse_mode="HTML")


# ────────────────────────────────────────────
#  /list
# ────────────────────────────────────────────
@router.message(Command("list"))
async def cmd_list(message: types.Message):
    await show_words_list(message, page=1, send_new=True)


@router.callback_query(F.data.startswith("list_page_"))
async def callback_list_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_words_list(callback.message, page=page, send_new=False, callback=callback)
    await callback.answer()


async def show_words_list(message: types.Message, page: int = 1, send_new: bool = True, callback=None):
    user_id = callback.from_user.id if callback else message.from_user.id
    ITEMS_PER_PAGE = 10

    async with AsyncSessionLocal() as session:
        total_items = await session.scalar(
            select(func.count(Word.id)).where(Word.user_id == user_id)
        ) or 0
        total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
        page = max(1, min(page, total_pages))

        stmt = (
            select(Word)
            .where(Word.user_id == user_id)
            .order_by(Word.added_at.desc())
            .offset((page - 1) * ITEMS_PER_PAGE)
            .limit(ITEMS_PER_PAGE)
        )
        result = await session.execute(stmt)
        words = result.scalars().all()

    if not words and total_items == 0:
        text = "📖 Ваш словник порожній. Надішліть мені слово, щоб розпочати!"
        keyboard = None
    else:
        text = f"📖 <b>Словник</b> (Сторінка {page}/{total_pages})\n\n"
        for i, w in enumerate(words):
            level_icons = ["🟢", "🟡", "🟠", "🔴", "🟣", "🔵"]
            if w.is_learned:
                icon = "✅"
            else:
                icon = level_icons[min(w.level, len(level_icons) - 1)]
            card = get_card_data(w)
            translation = card.get("translation", "—")
            text += f"{icon} <b>{w.word}</b> — {translation}\n"
        keyboard = get_pagination_keyboard(page, total_pages, prefix="list") if total_pages > 1 else None

    if send_new:
        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")


# ────────────────────────────────────────────
#  /delete
# ────────────────────────────────────────────
@router.message(Command("delete"))
async def cmd_delete(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("ℹ️ Використання: /delete <слово>\nНаприклад: /delete apple")
        return

    word_to_delete = args[1].strip().lower()
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = select(Word).where(Word.user_id == user_id, Word.word.ilike(word_to_delete))
        result = await session.execute(stmt)
        word = result.scalars().first()

        if word:
            await session.delete(word)
            await session.commit()
            await message.answer(f"✅ Слово <b>{word_to_delete}</b> видалено з вашого словника.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Слово <b>{word_to_delete}</b> не знайдено.", parse_mode="HTML")


@router.callback_query(F.data.startswith("delete_word_"))
async def callback_delete_word(callback: types.CallbackQuery):
    word_id = int(callback.data.split("_")[2])

    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)
        if word and word.user_id == callback.from_user.id:
            word_str = word.word
            await session.delete(word)
            await session.commit()
            await callback.message.edit_text(f"🗑 Слово <b>{word_str}</b> видалено.", parse_mode="HTML")
        else:
            await callback.answer("Слово не знайдено або вже видалено.")
            return
    await callback.answer()


# ────────────────────────────────────────────
#  /practice
# ────────────────────────────────────────────
@router.message(Command("practice"))
async def cmd_practice(message: types.Message):
    user_id = message.from_user.id

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Word)
            .where(Word.user_id == user_id, Word.is_learned == False)
            .order_by(func.random())
            .limit(1)
        )
        result = await session.execute(stmt)
        word = result.scalars().first()

    if not word:
        await message.answer("🎉 Усі слова вивчені! Додай нові слова для тренування.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Пам'ятаю", callback_data=f"review_yes_{word.id}"),
            InlineKeyboardButton(text="❌ Забув", callback_data=f"review_no_{word.id}")
        ]
    ])

    await message.answer(
        f"🏋️ <b>Тренування</b>\n\n"
        f"Як перекладається <b>{word.word.upper()}</b>?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )


# ────────────────────────────────────────────
#  Додавання нового слова (catch-all, лише текст без "/")
# ────────────────────────────────────────────
@router.message(F.text, ~F.text.startswith("/"))
async def add_word_handler(message: types.Message, state: FSMContext):
    # Якщо юзер зараз у стані редагування - не перехоплювати
    current_state = await state.get_state()
    if current_state is not None:
        return

    user_id = message.from_user.id
    input_text = message.text.strip()

    if not input_text:
        return

    # Швидка перевірка на дублікат (для миттєвої відповіді)
    async with AsyncSessionLocal() as session:
        stmt = select(Word).where(
            Word.user_id == user_id,
            Word.word.ilike(input_text.lower())
        )
        result = await session.execute(stmt)
        existing_word = result.scalars().first()
        if existing_word:
            card = get_card_data(existing_word)
            await message.reply(
                f"ℹ️ Слово <b>{input_text}</b> вже в базі (рівень {existing_word.level}).\n"
                f"Переклад: {card.get('translation', '—')}",
                parse_mode="HTML"
            )
            return

    processing_msg = await message.reply("⏳ Аналізую слово та генерую картку...")

    result = await process_new_word(user_id, input_text, source="telegram")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit_trans_{result['word_id']}"),
            InlineKeyboardButton(text="🗑 Видалити", callback_data=f"delete_word_{result['word_id']}")
        ]
    ])

    await processing_msg.edit_text(result["response_text"], parse_mode="HTML", reply_markup=keyboard)


# ────────────────────────────────────────────
#  Колбек повторення (Пам'ятаю / Забув)
# ────────────────────────────────────────────
@router.callback_query(F.data.startswith("review_"))
async def process_review_callback(callback: types.CallbackQuery):
    parts = callback.data.split("_")
    action = parts[1]   # "yes" або "no"
    word_id = int(parts[2])

    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)

        if not word:
            await callback.answer("Слово не знайдено.")
            return

        now = datetime.now(timezone.utc)
        card_data = get_card_data(word)

        if action == "yes":
            word.level += 1
            if word.level >= len(REVIEW_INTERVALS):
                word.is_learned = True
                msg_text = (
                    f"🎉 <b>{word.word.upper()}</b> — повністю вивчено!\n\n"
                    f"🇺🇦 {card_data.get('translation', '')}"
                )
            else:
                word.next_review = now + REVIEW_INTERVALS[word.level]
                interval = REVIEW_INTERVALS[word.level]
                # Форматуємо інтервал красиво
                if interval.days >= 1:
                    interval_str = f"{interval.days} дн."
                else:
                    interval_str = f"{interval.seconds // 3600} год."
                msg_text = (
                    f"✅ <b>{word.word.upper()}</b>\n\n"
                    f"🇺🇦 {card_data.get('translation', '')}\n"
                    f"⏰ Наступне повторення: через {interval_str}"
                )
        else:
            word.level = 0
            word.next_review = now + REVIEW_INTERVALS[0]
            msg_text = (
                f"🔄 <b>{word.word.upper()}</b>\n\n"
                f"🇺🇦 {card_data.get('translation', '')}\n"
                f"📖 <i>{card_data.get('example', '')}</i>\n\n"
                f"⏰ Повторимо через 4 год."
            )

        word.is_waiting_for_review = False
        session.add(word)

        user = await session.get(User, callback.from_user.id)
        if user:
            await update_user_activity(session, user)

        await session.commit()

    await callback.message.edit_text(msg_text, parse_mode="HTML")
    await callback.answer()


# ────────────────────────────────────────────
#  Редагування перекладу (FSM)
# ────────────────────────────────────────────
@router.callback_query(F.data.startswith("edit_trans_"))
async def callback_edit_trans(callback: types.CallbackQuery, state: FSMContext):
    word_id = int(callback.data.split("_")[2])
    await state.update_data(edit_word_id=word_id)
    await state.set_state(EditTranslationState.waiting_for_translation)
    await callback.message.answer("📝 Введіть новий переклад:")
    await callback.answer()


@router.message(EditTranslationState.waiting_for_translation)
async def process_new_translation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    word_id = data.get("edit_word_id")
    new_translation = message.text.strip()

    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)
        if word and word.user_id == message.from_user.id:
            card_data = get_card_data(word)
            card_data['translation'] = new_translation
            word.llm_response = card_data
            session.add(word)
            await session.commit()

            await message.answer(
                f"✅ Переклад <b>{word.word}</b> оновлено:\n🇺🇦 {new_translation}",
                parse_mode="HTML"
            )
        else:
            await message.answer("❌ Слово не знайдено.")

    await state.clear()


# ────────────────────────────────────────────
#  Ігнорування натискання на "сторінку" у пагінації
# ────────────────────────────────────────────
@router.callback_query(F.data == "ignore")
async def callback_ignore(callback: types.CallbackQuery):
    await callback.answer()

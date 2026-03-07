import json
import random
import math
from datetime import datetime, timezone, timedelta
from aiogram import Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select, func, or_
from database import AsyncSessionLocal
from models import Word, User
from llm import generate_word_card
from scheduler import REVIEW_INTERVALS
from states import EditTranslationState
from utils import update_user_activity, get_pagination_keyboard

router = Router()

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
        "Корисні команди:\n"
        "/stats - Твоя статистика\n"
        "/list - Список усіх слів\n"
        "/practice - Миттєве тренування\n"
        "/delete <слово> - Видалити слово"
    )

@router.message(F.text, ~F.text.startswith("/"))
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
            llm_response=card_data,  # Assuming JSONB mapping accepts dict directly
            next_review=now + REVIEW_INTERVALS[0] # Перше повторення через 4 години
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
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редагувати переклад", callback_data=f"edit_trans_{new_word.id}"),
            InlineKeyboardButton(text="❌ Видалити", callback_data=f"delete_word_{new_word.id}")
        ]
    ])
    
    await processing_msg.edit_text(response_text, parse_mode="HTML", reply_markup=keyboard)

@router.callback_query(F.data.startswith("review_"))
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
            # Якщо `llm_response` буде збережено як JSONB або словник у зв'язці з базою,
            # тут потрібно перевірити, чи це строка, чи вже об'єкт
            if isinstance(word.llm_response, str):
                card_data = json.loads(word.llm_response)
            else:
                card_data = word.llm_response or {}
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
        
        user = await session.get(User, callback.from_user.id)
        if user:
            await update_user_activity(session, user)
            
        await session.commit()
        
    await callback.message.edit_text(msg_text, parse_mode="HTML")
    await callback.answer()

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    user_id = message.from_user.id
    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        
        # Загально слів
        total_stmt = select(func.count(Word.id)).where(Word.user_id == user_id)
        total_words = await session.scalar(total_stmt) or 0
        
        # Вивчено слів
        learned_stmt = select(func.count(Word.id)).where(Word.user_id == user_id, Word.is_learned == True)
        learned_words = await session.scalar(learned_stmt) or 0
        
        # Слова на сьогодні
        now = datetime.now(timezone.utc)
        today_stmt = select(func.count(Word.id)).where(
            Word.user_id == user_id, 
            Word.is_learned == False,
            Word.next_review <= now + timedelta(days=1)
        )
        words_today = await session.scalar(today_stmt) or 0
        
        streak = user.current_streak if user else 0
        max_streak = user.max_streak if user else 0
        
    stats_text = (
        f"📊 <b>Твоя статистика:</b>\n"
        f"───────────────\n"
        f"📝 Всього слів у базі: <b>{total_words}</b>\n"
        f"🎓 Повністю вивчено: <b>{learned_words}</b>\n"
        f"📅 До повторення сьогодні: <b>{words_today}</b>\n\n"
        f"🔥 Поточний стрік: <b>{streak} днів</b>\n"
        f"🏆 Найкращий стрік: <b>{max_streak} днів</b>\n"
    )
    await message.answer(stats_text, parse_mode="HTML")

@router.message(Command("delete"))
async def cmd_delete(message: types.Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Використання: /delete <слово>")
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
            await message.answer(f"✅ Слово <b>{word_to_delete}</b> успішно видалено.", parse_mode="HTML")
        else:
            await message.answer(f"❌ Слово <b>{word_to_delete}</b> не знайдено у вашому словнику.", parse_mode="HTML")

@router.callback_query(F.data.startswith("delete_word_"))
async def callback_delete_word(callback: types.CallbackQuery):
    word_id = int(callback.data.split("_")[2])
    
    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)
        if word and word.user_id == callback.from_user.id:
            word_str = word.word
            await session.delete(word)
            await session.commit()
            await callback.message.edit_text(f"✅ Слово <b>{word_str}</b> видалено.", parse_mode="HTML")
        else:
            await callback.answer("Слово не знайдено або вже видалено.")
    await callback.answer()

@router.message(Command("list"))
async def cmd_list(message: types.Message):
    await show_words_list(message.chat.id, message.from_user.id, page=1, send_new=True)

@router.callback_query(F.data.startswith("list_page_"))
async def callback_list_page(callback: types.CallbackQuery):
    page = int(callback.data.split("_")[2])
    await show_words_list(callback.message.chat.id, callback.from_user.id, page=page, send_new=False, message_id=callback.message.message_id)
    await callback.answer()

async def show_words_list(chat_id: int, user_id: int, page: int = 1, send_new: bool = True, message_id: int = None):
    from main import bot
    ITEMS_PER_PAGE = 10
    
    async with AsyncSessionLocal() as session:
        total_stmt = select(func.count(Word.id)).where(Word.user_id == user_id)
        total_items = await session.scalar(total_stmt) or 0
        total_pages = math.ceil(total_items / ITEMS_PER_PAGE) if total_items > 0 else 1
        page = max(1, min(page, total_pages))
        
        stmt = select(Word).where(Word.user_id == user_id).order_by(Word.id.desc()).offset((page - 1) * ITEMS_PER_PAGE).limit(ITEMS_PER_PAGE)
        result = await session.execute(stmt)
        words = result.scalars().all()
        
    if not words:
        text = "Ваш словник порожній."
        keyboard = None
    else:
        text = f"📖 <b>Ваш словник (Сторінка {page}/{total_pages}):</b>\n\n"
        for w in words:
            status = "✅" if w.is_learned else f"⏳ {w.level}"
            text += f"• <b>{w.word}</b> [{status}]\n"
        keyboard = get_pagination_keyboard(page, total_pages, prefix="list") if total_pages > 1 else None

    if send_new:
        await bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="HTML")
    else:
        await bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard, parse_mode="HTML")

@router.message(Command("practice"))
async def cmd_practice(message: types.Message):
    user_id = message.from_user.id
    
    async with AsyncSessionLocal() as session:
        # Беремо 1 випадкове ще не вивчене слово
        stmt = select(Word).where(
            Word.user_id == user_id,
            Word.is_learned == False
        ).order_by(func.random()).limit(1)
        result = await session.execute(stmt)
        word = result.scalars().first()
        
    if not word:
        await message.answer("У вас немає не вивчених слів для тренування! Додайте нові слова.")
        return
        
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Пам'ятаю", callback_data=f"review_yes_{word.id}"),
            InlineKeyboardButton(text="❌ Забув", callback_data=f"review_no_{word.id}")
        ]
    ])
    
    await message.answer(
        f"🏃‍♂️ <b>Практика:</b>\nТи пам'ятаєш переклад слова <b>{word.word.upper()}</b>?",
        reply_markup=keyboard,
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("edit_trans_"))
async def callback_edit_trans(callback: types.CallbackQuery, state: FSMContext):
    word_id = int(callback.data.split("_")[2])
    await state.update_data(edit_word_id=word_id)
    await state.set_state(EditTranslationState.waiting_for_translation)
    await callback.message.answer("📝 Надішліть новий переклад для цього слова:")
    await callback.answer()

@router.message(EditTranslationState.waiting_for_translation)
async def process_new_translation(message: types.Message, state: FSMContext):
    data = await state.get_data()
    word_id = data.get("edit_word_id")
    new_translation = message.text.strip()
    
    async with AsyncSessionLocal() as session:
        word = await session.get(Word, word_id)
        if word and word.user_id == message.from_user.id:
            try:
                card_data = word.llm_response if isinstance(word.llm_response, dict) else json.loads(word.llm_response)
            except:
                card_data = {}
                
            card_data['translation'] = new_translation
            word.llm_response = card_data
            session.add(word)
            await session.commit()
            
            await message.answer(f"✅ Переклад для <b>{word.word}</b> успішно оновлено на: {new_translation}", parse_mode="HTML")
        else:
            await message.answer("❌ Слово не знайдено.")
            
    await state.clear()

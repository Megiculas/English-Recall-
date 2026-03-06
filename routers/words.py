import json
from datetime import datetime, timezone
from aiogram import Router, types, F
from aiogram.filters import CommandStart
from sqlalchemy import select
from database import AsyncSessionLocal
from models import Word
from llm import generate_word_card
from scheduler import REVIEW_INTERVALS

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer(
        "Привіт! Я твій персональний бот для вивчення англійської. 🇬🇧\n"
        "Просто надішли мені незнайоме слово або фразу, і я додам його до твоєї бази "
        "з прикладами, транскрипцією та запущу інтервальне повторення!"
    )

@router.message()
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
        now = datetime.now(timezone.utc)
        new_word = Word(
            user_id=user_id,
            word=input_text.lower(),
            context_given=input_text,
            llm_response=json.dumps(card_data, ensure_ascii=False),
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
    
    await processing_msg.edit_text(response_text, parse_mode="HTML")

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
        await session.commit()
        
    await callback.message.edit_text(msg_text, parse_mode="HTML")
    await callback.answer()

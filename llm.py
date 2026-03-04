import json
from openai import AsyncOpenAI
from config import settings

# Ініціалізація асинхронного клієнта OpenAI (для OpenRouter)
client = AsyncOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=settings.OPENROUTER_API_KEY,
)

SYSTEM_PROMPT = """Ти - експерт з англійської мови. Користувач надсилає тобі слово або фразу (можливо з контекстом).
Твоє завдання - надати структуровану відповідь у форматі JSON.
Відповідь має містити:
- "translation": переклад українською мовою
- "transcription": транскрипція (наприклад, [əˈbændən])
- "example": речення-приклад використання англійською мовою (бажано врахувати контекст, якщо він наданий)
- "synonyms": 2-3 синоніми через кому
- "tags": 1-2 теги (наприклад, #бізнес, #емоції)

Поверни ТІЛЬКИ валідний JSON без markdown-коду або додаткових коментарів, наприклад:
{
  "translation": "залишати, кидати",
  "transcription": "[əˈbændən]",
  "example": "She abandoned her car in the middle of the road.",
  "synonyms": "leave, desert, give up",
  "tags": "#щоденне"
}
"""

async def generate_word_card(word_input: str) -> str:
    """Відправляє запит до LLM і повертає JSON-рядок з карткою слова."""
    try:
        response = await client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Опрацюй це слово/фразу: {word_input}"}
            ],
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Помилка при запиті до OpenRouter: {e}")
        return json.dumps({
            "translation": "Помилка при перекладі",
            "transcription": "[-]",
            "example": "-",
            "synonyms": "-",
            "tags": "#error"
        })

import logging
from aiogram import F, Router
from aiogram.types import Message

from database.database import (
    get_active_chat_id, create_chat, add_to_history,
    get_history, get_chat_prompt
)
from ollama_client.ollama_client import get_ollama_response

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.text)
async def handle_text(message: Message):
    """Обработка текстовых сообщений (не команд)"""
    if message.text.startswith('/'):
        return  # Игнорируем команды — их обрабатывают другие хендлеры

    telegram_id = message.from_user.id
    user_text = message.text

    # Получаем или создаём активный чат
    chat_id = await get_active_chat_id(telegram_id)
    if not chat_id:
        chat_id = await create_chat(telegram_id, "Основной")
        logger.info(f"Создан чат по умолчанию для {telegram_id}, chat_id={chat_id}")

    # Сохраняем сообщение пользователя в историю
    await add_to_history(chat_id, "user", user_text)
    await message.answer("🤔 Думаю...")

    try:
        history = await get_history(chat_id)
        system_prompt = await get_chat_prompt(chat_id)
        answer = await get_ollama_response(history, system_prompt=system_prompt)

        await add_to_history(chat_id, "assistant", answer)
        await message.answer(answer)

    except Exception as e:
        logger.error(f"❌ Ошибка работы с Ollama: {e}")
        await message.answer("⚠️ Не удалось получить ответ. Попробуйте позже.")
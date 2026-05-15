import aiohttp
import logging
from typing import Optional

from config.config import OLLAMA_URL, OLLAMA_MODEL, DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


# ==================== ОСНОВНОЙ ЗАПРОС ====================

async def get_ollama_response(
        messages: list[dict],
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.7,
        timeout: int = 120
) -> str:
    """
    Отправляет запрос в Ollama через Chat API.

    :param messages: Список сообщений в формате [{"role": "user", "content": "..."}]
    :param system_prompt: Системный промпт (добавляется первым сообщением)
    :param model: Название модели (по умолчанию из config)
    :param temperature: Температура генерации (0.0 - 1.0)
    :param timeout: Таймаут запроса в секундах
    :return: Текст ответа от модели или сообщение об ошибке
    """
    # Формируем сообщения в формате Ollama Chat API
    ollama_messages = []

    # Добавляем системный промпт первым сообщением
    if system_prompt:
        ollama_messages.append({"role": "system", "content": system_prompt})
    elif DEFAULT_SYSTEM_PROMPT:
        ollama_messages.append({"role": "system", "content": DEFAULT_SYSTEM_PROMPT})

    # Добавляем историю диалога
    ollama_messages.extend(messages)

    # Параметры запроса
    payload = {
        "model": model or OLLAMA_MODEL,
        "messages": ollama_messages,
        "stream": False,  # Получаем ответ целиком, не потоком
        "options": {
            "temperature": temperature,
            "num_predict": 2048,  # Максимальное количество токенов в ответе
        }
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                    OLLAMA_URL,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                # Проверяем статус ответа
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"❌ Ollama HTTP {response.status}: {error_text}")
                    return f"⚠️ Ошибка сервера ({response.status}): {error_text[:200]}"

                # Парсим JSON ответ
                data = await response.json()

                # Извлекаем текст ответа (правильный путь для Chat API)
                content = data.get("message", {}).get("content", "").strip()

                if not content:
                    logger.warning("⚠️ Пустой ответ от Ollama")
                    return "🤔 Не удалось сгенерировать ответ. Попробуйте перефразировать запрос."

                return content

    except aiohttp.ClientConnectionError:
        logger.error("❌ Не удалось подключиться к Ollama. Проверьте, запущен ли сервер.")
        return "⚠️ Не удалось подключиться к серверу. Убедитесь, что Ollama запущен."

    except aiohttp.ClientTimeout:
        logger.error(f"❌ Таймаут запроса к Ollama (> {timeout}с)")
        return "⏱ Ответ занимает слишком много времени. Попробуйте позже или упростите запрос."

    except aiohttp.ClientError as e:
        logger.error(f"❌ Ошибка HTTP-клиента: {e}")
        return f"⚠️ Сетевая ошибка: {str(e)[:150]}"

    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при запросе к Ollama: {e}", exc_info=True)
        return "⚠️ Произошла непредвиденная ошибка. Попробуйте позже."
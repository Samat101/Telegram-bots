import asyncpg
import logging
from typing import Optional

from config.config import DB_URL, DEFAULT_SYSTEM_PROMPT

logger = logging.getLogger(__name__)
pool: Optional[asyncpg.Pool] = None

# Кэш промптов в оперативной памяти
chat_prompts: dict[int, str] = {}
MAX_HISTORY_MESSAGES = 10


# ==================== ИНИЦИАЛИЗАЦИЯ ====================

async def init_db():
    """Инициализация пула подключений и создание таблиц"""
    global pool

    try:
        pool = await asyncpg.create_pool(DB_URL)
        logger.info("✅ Успешное подключение к базе данных")

        async with pool.acquire() as conn:
            # Таблица пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    login TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    telegram_id BIGINT UNIQUE NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Таблица чатов/сессий
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chats (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL DEFAULT 'Новый чат',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
                )
            """)

            # Таблица истории сообщений
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id SERIAL PRIMARY KEY,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
            """)

            # Таблица активных сессий пользователей
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_sessions (
                    telegram_id BIGINT PRIMARY KEY,
                    active_chat_id INTEGER REFERENCES chats(id),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Таблица кастомных системных промптов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_prompts (
                    chat_id INTEGER PRIMARY KEY,
                    system_prompt TEXT NOT NULL,
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                )
            """)

            # Индексы для ускорения поиска
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chats_user_id ON chats(user_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id ON chat_history(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_chat_prompts_chat_id ON chat_prompts(chat_id)")

            logger.info("✅ Все таблицы базы данных проверены/созданы")

    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise


async def close_db():
    """Закрытие пула подключений"""
    global pool
    if pool:
        await pool.close()
        logger.info("🔌 Подключения к БД закрыты")


# ==================== ПОЛЬЗОВАТЕЛИ ====================

async def check_user_authorized(telegram_id: int) -> bool:
    """Проверка, зарегистрирован ли пользователь"""
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT telegram_id FROM users WHERE telegram_id = $1",
            telegram_id
        )
        return result is not None


async def register_user(telegram_id: int, login: str, password_hash: str) -> tuple[bool, str]:
    """
    Регистрация нового пользователя.
    Возвращает (success: bool, message: str)
    """
    async with pool.acquire() as conn:
        # Проверка на занятый логин
        if await conn.fetchval("SELECT login FROM users WHERE login = $1", login):
            return False, "❌ Этот логин уже занят"

        # Проверка на привязанный Telegram
        if await conn.fetchval("SELECT login FROM users WHERE telegram_id = $1", telegram_id):
            return False, "❌ Этот Telegram уже привязан к другому аккаунту"

        try:
            await conn.execute(
                "INSERT INTO users (login, password_hash, telegram_id) VALUES ($1, $2, $3)",
                login, password_hash, telegram_id
            )
            logger.info(f"✅ Пользователь {login} (tg:{telegram_id}) зарегистрирован")
            return True, "✅ Регистрация успешна!"
        except Exception as e:
            logger.error(f"❌ Ошибка при регистрации: {e}")
            return False, f"❌ Ошибка базы данных: {str(e)}"


# ==================== УПРАВЛЕНИЕ ЧАТАМИ ====================

async def get_active_chat_id(telegram_id: int) -> Optional[int]:
    """Получить ID активного чата пользователя"""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT active_chat_id FROM user_sessions WHERE telegram_id = $1",
            telegram_id
        )


async def set_active_chat(telegram_id: int, chat_id: int):
    """Установить активный чат для пользователя (upsert)"""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO user_sessions (telegram_id, active_chat_id)
            VALUES ($1, $2)
            ON CONFLICT (telegram_id) 
            DO UPDATE SET active_chat_id = $2, updated_at = NOW()
        """, telegram_id, chat_id)


async def create_chat(telegram_id: int, name: str = "Новый чат") -> int:
    """Создать новый чат и вернуть его ID"""
    async with pool.acquire() as conn:
        chat_id = await conn.fetchval("""
            INSERT INTO chats (user_id, name)
            VALUES ($1, $2)
            RETURNING id
        """, telegram_id, name)

        # Автоматически делаем новый чат активным
        await set_active_chat(telegram_id, chat_id)
        return chat_id


async def get_user_chats(telegram_id: int) -> list[dict]:
    """Получить список всех чатов пользователя с количеством сообщений"""
    async with pool.acquire() as conn:
        rows = await conn.fetch(""" 
            SELECT id, name, created_at, 
                   (SELECT COUNT(*) FROM chat_history WHERE chat_id = chats.id) as msg_count
            FROM chats 
            WHERE user_id = $1 
            ORDER BY updated_at DESC
        """, telegram_id)
        return [dict(row) for row in rows]


async def delete_chat(telegram_id: int, chat_id: int) -> bool:
    """
    Удалить чат.
    Возвращает True, если чат принадлежал пользователю и был удалён.
    """
    async with pool.acquire() as conn:
        # Проверяем принадлежность чата
        exists = await conn.fetchval(
            "SELECT id FROM chats WHERE id = $1 AND user_id = $2",
            chat_id, telegram_id
        )
        if not exists:
            return False

        # Если это был активный чат — сбрасываем active_chat_id
        await conn.execute(
            "UPDATE user_sessions SET active_chat_id = NULL WHERE telegram_id = $1 AND active_chat_id = $2",
            telegram_id, chat_id
        )

        # Удаляем чат (CASCADE удалит связанные записи)
        await conn.execute("DELETE FROM chats WHERE id = $1", chat_id)
        return True


async def rename_chat(telegram_id: int, chat_id: int, new_name: str) -> bool:
    """Переименовать чат"""
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE chats 
            SET name = $1, updated_at = NOW()
            WHERE id = $2 AND user_id = $3
        """, new_name, chat_id, telegram_id)
        return result == "UPDATE 1"


async def get_chat_name(chat_id: int) -> Optional[str]:
    """Получить имя чата по ID"""
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT name FROM chats WHERE id = $1", chat_id)


# ==================== СИСТЕМНЫЕ ПРОМПТЫ ====================

async def get_chat_prompt(chat_id: int) -> str:
    """Получить системный промпт для чата (из кэша или БД)"""
    # Сначала пробуем из оперативной памяти
    if chat_id in chat_prompts:
        return chat_prompts[chat_id]

    # Потом из БД
    async with pool.acquire() as conn:
        prompt = await conn.fetchval(
            "SELECT system_prompt FROM chat_prompts WHERE chat_id = $1",
            chat_id
        )
        if prompt:
            chat_prompts[chat_id] = prompt
            return prompt

    # Если не найдено — возвращаем дефолтный
    return DEFAULT_SYSTEM_PROMPT


async def set_chat_prompt(chat_id: int, prompt: str) -> bool:
    """Установить кастомный промпт для чата"""
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO chat_prompts (chat_id, system_prompt)
            VALUES ($1, $2)
            ON CONFLICT (chat_id) 
            DO UPDATE SET system_prompt = $2, updated_at = NOW()
        """, chat_id, prompt)

    chat_prompts[chat_id] = prompt  # обновляем кэш
    return True


async def reset_chat_prompt(chat_id: int) -> bool:
    """Сбросить промпт чата на дефолтный"""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chat_prompts WHERE chat_id = $1", chat_id)

    chat_prompts.pop(chat_id, None)  # удаляем из кэша
    return True


# ==================== ИСТОРИЯ СООБЩЕНИЙ ====================

async def add_to_history(chat_id: int, role: str, content: str):
    """
    Добавляет сообщение в историю чата и удаляет старые при превышении лимита.
    """
    async with pool.acquire() as conn:
        # Вставляем новое сообщение
        await conn.execute(
            "INSERT INTO chat_history (chat_id, role, content) VALUES ($1, $2, $3)",
            chat_id, role, content
        )

        # Считаем количество сообщений
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chat_history WHERE chat_id = $1",
            chat_id
        )

        # Если больше лимита — удаляем самые старые
        if count > MAX_HISTORY_MESSAGES:
            to_delete = count - MAX_HISTORY_MESSAGES
            await conn.execute("""
                DELETE FROM chat_history 
                WHERE chat_id = $1 
                AND id IN (
                    SELECT id FROM chat_history 
                    WHERE chat_id = $1 
                    ORDER BY id ASC 
                    LIMIT $2
                )
            """, chat_id, to_delete)


async def get_history(chat_id: int) -> list[dict]:
    """
    Возвращает историю чата в формате для Ollama.
    :return: [{"role": "user", "content": "..."}, ...]
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM chat_history WHERE chat_id = $1 ORDER BY id ASC",
            chat_id
        )
        return [{"role": row["role"], "content": row["content"]} for row in rows]


async def clear_history(chat_id: int):
    """Полная очистка истории конкретного чата"""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM chat_history WHERE chat_id = $1", chat_id)
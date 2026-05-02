import bcrypt
import logging
from aiogram import F, Router
from aiogram.types import Message
from aiogram.filters import CommandStart, Command

# Импорт функций из других модулей
from database.database import (
    check_user_authorized, get_active_chat_id, create_chat,
    get_user_chats, delete_chat, rename_chat, get_chat_name,
    get_chat_prompt, set_chat_prompt, reset_chat_prompt,
    clear_history, set_active_chat, pool
)


router = Router()
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def start(message: Message):
    """Команда /start — приветствие"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        chat_id = await create_chat(telegram_id, "Основной")

    await message.answer(
        "👋 Привет! Я бот с памятью и мульти-чатами.\n\n"
        "Просто напишите что-нибудь — я отвечу.\n"
        "Команды для управления: /help\n"
        "Если не зарегистрированы: /reg логин пароль"
    )


@router.message(Command("help"))
async def help_command(message: Message):
    """Справка по командам"""
    await message.answer(
        "📚 Доступные команды:\n\n"
        "🔐 Регистрация:\n"
        "  /reg логин пароль — регистрация аккаунта\n\n"
        "💬 Управление чатами:\n"
        "  /newchat [имя] — создать новый чат\n"
        "  /chats — список всех чатов\n"
        "  /switch <ID> — переключиться на чат по ID\n"
        "  /renamechat <ID> имя — переименовать чат\n"
        "  /deletechat <ID> — удалить чат с историей\n"
        "  /current — показать текущий чат\n\n"
        "⚙️ Настройки:\n"
        "  /clear — очистить историю текущего чата\n"
        "  /prompt текст — установить системный промпт\n"
        "  /showprompt — показать текущий промпт\n"
        "  /resetprompt — сбросить промпт на дефолтный"
    )


@router.message(Command("clear"))
async def cmd_clear(message: Message):
    """Очистить историю текущего чата"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        return await message.answer("⚠️ У вас нет активного чата. Создайте через /newchat")

    chat_name = await get_chat_name(chat_id)
    await clear_history(chat_id)
    await message.answer(f"🗑 История чата «{chat_name}» очищена! Начинаем с чистого листа.")


@router.message(Command("reg"))
async def cmd_register(message: Message):
    """Регистрация: /reg логин пароль"""


    args = message.text.split()
    if len(args) < 3:
        return await message.answer("❌ Формат: /reg логин пароль")

    login, password = args[1], args[2]
    telegram_id = message.from_user.id

    logger.info(f"Попытка регистрации: login={login}, telegram_id={telegram_id}")
    pwd_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    try:
        async with pool.acquire() as conn:
            if await conn.fetchval("SELECT login FROM users WHERE login = $1", login):
                return await message.answer("❌ Этот логин уже занят")

            if await conn.fetchval("SELECT login FROM users WHERE telegram_id = $1", telegram_id):
                return await message.answer("❌ Этот Telegram уже привязан к аккаунту")

            await conn.execute(
                "INSERT INTO users (login, password_hash, telegram_id) VALUES ($1, $2, $3)",
                login, pwd_hash, telegram_id
            )
            logger.info(f"✅ Пользователь {login} зарегистрирован")
            await message.answer("✅ Регистрация успешна! Теперь вы можете отправлять запросы.")

    except Exception as e:
        logger.error(f"❌ Ошибка регистрации: {e}")
        await message.answer(f"❌ Ошибка базы данных: {str(e)}")


@router.message(Command("newchat"))
async def cmd_newchat(message: Message):
    """Создать новый чат"""
    telegram_id = message.from_user.id
    args = message.text.split(maxsplit=1)

    chat_count = len(await get_user_chats(telegram_id))
    chat_name = args[1].strip()[:50] if len(args) > 1 else f"Чат #{chat_count + 1}"

    chat_id = await create_chat(telegram_id, chat_name)
    await message.answer(f"✅ Создан чат: «{chat_name}» (ID: {chat_id})\nТеперь вы общаетесь в нём.")


@router.message(Command("chats"))
async def cmd_list_chats(message: Message):
    """Список чатов пользователя"""
    telegram_id = message.from_user.id
    chats = await get_user_chats(telegram_id)
    active_chat_id = await get_active_chat_id(telegram_id)

    if not chats:
        return await message.answer("📭 У вас пока нет чатов. Создайте первый: /newchat")

    text = "📋 Ваши чаты:\n\n"
    for chat in chats:
        marker = "🟢" if chat["id"] == active_chat_id else "⚪"
        text += f"{marker} {chat['id']} — {chat['name']}\n   📊 Сообщений: {chat['msg_count']}\n"

    text += "\n💡 Используйте /switch <ID> для переключения"
    await message.answer(text)


@router.message(Command("switch"))
async def cmd_switch(message: Message):
    """Переключиться на чат по ID"""
    telegram_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        return await message.answer("❌ Формат: /switch <ID>\nID можно посмотреть в /chats")

    try:
        chat_id = int(args[1])
    except ValueError:
        return await message.answer("❌ ID должен быть числом")

    chats = await get_user_chats(telegram_id)
    if not any(c["id"] == chat_id for c in chats):
        return await message.answer("❌ Чат с таким ID не найден")

    await set_active_chat(telegram_id, chat_id)
    chat_name = await get_chat_name(chat_id)
    await message.answer(f"🔄 Переключились на чат: «{chat_name}» (ID: {chat_id})")


@router.message(Command("deletechat"))
async def cmd_delete_chat(message: Message):
    """Удалить чат по ID"""
    telegram_id = message.from_user.id
    args = message.text.split()

    if len(args) < 2:
        return await message.answer("❌ Формат: /deletechat <ID>")

    try:
        chat_id = int(args[1])
    except ValueError:
        return await message.answer("❌ ID должен быть числом")

    success = await delete_chat(telegram_id, chat_id)
    if success:
        await message.answer(f"🗑 Чат ID {chat_id} удалён вместе с историей")
    else:
        await message.answer("❌ Не удалось удалить чат. Проверьте ID")


@router.message(Command("renamechat"))
async def cmd_rename_chat(message: Message):
    """Переименовать чат: /renamechat <ID> Новое имя"""
    telegram_id = message.from_user.id
    args = message.text.split(maxsplit=2)

    if len(args) < 3:
        return await message.answer("❌ Формат: /renamechat <ID> Новое имя")

    try:
        chat_id = int(args[1])
    except ValueError:
        return await message.answer("❌ ID должен быть числом")

    new_name = args[2].strip()
    if not new_name or len(new_name) > 50:
        return await message.answer("❌ Имя чата должно быть от 1 до 50 символов")

    success = await rename_chat(telegram_id, chat_id, new_name)
    if success:
        await message.answer(f"✏️ Чат переименован в: «{new_name}»")
    else:
        await message.answer("❌ Не удалось переименовать. Проверьте ID")


@router.message(Command("current"))
async def cmd_current_chat(message: Message):
    """Показать текущий активный чат"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        chat_id = await create_chat(telegram_id, "Основной")
        await message.answer(f"🆕 Создан чат по умолчанию: «Основной» (ID: {chat_id})")
        return

    chat_name = await get_chat_name(chat_id)
    await message.answer(
        f"📍 Сейчас вы в чате: «{chat_name}» (ID: {chat_id})\n\n"
        f"Для смены: /switch <ID>"
    )


@router.message(Command("prompt"))
async def cmd_set_prompt(message: Message):
    """Установить системный промпт: /prompt Ваш текст"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        return await message.answer("⚠️ Сначала создайте чат через /newchat")

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer(
            "❌ Формат: /prompt Ваш системный промпт\n"
            "Пример: /prompt Ты — эксперт по Python. Отвечай с примерами кода."
        )

    new_prompt = args[1].strip()
    if len(new_prompt) > 500:
        return await message.answer("❌ Промпт слишком длинный (макс. 500 символов)")

    await set_chat_prompt(chat_id, new_prompt)
    await message.answer(f"✅ Промпт обновлён для чата #{chat_id}")


@router.message(Command("showprompt"))
async def cmd_show_prompt(message: Message):
    """Показать текущий системный промпт"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        return await message.answer("⚠️ У вас нет активного чата")

    prompt = await get_chat_prompt(chat_id)
    chat_name = await get_chat_name(chat_id)

    await message.answer(
        f"📋 Промпт для чата «{chat_name}» (ID: {chat_id}):\n\n"
        f"```\n{prompt}\n```",
        parse_mode="Markdown"
    )


@router.message(Command("resetprompt"))
async def cmd_reset_prompt(message: Message):
    """Сбросить промпт на дефолтный"""
    telegram_id = message.from_user.id
    chat_id = await get_active_chat_id(telegram_id)

    if not chat_id:
        return await message.answer("⚠️ У вас нет активного чата")

    await reset_chat_prompt(chat_id)
    await message.answer(f"🔄 Промпт сброшен на дефолтный для чата #{chat_id}")
from database.database import check_user_authorized

PUBLIC_COMMANDS = (
    '/start', '/reg', '/clear', '/newchat', '/chats',
    '/switch', '/deletechat', '/renamechat', '/current', '/help'
)


async def auth_middleware(handler, event, data):
    """Проверяет авторизацию, кроме публичных команд"""

    # Пропускаем публичные команды
    if event.text and any(event.text.startswith(cmd) for cmd in PUBLIC_COMMANDS):
        return await handler(event, data)

    telegram_id = event.from_user.id
    if not await check_user_authorized(telegram_id):
        await event.answer("⛔ Вы не зарегистрированы. Сначала выполните /reg логин пароль")
        return

    return await handler(event, data)
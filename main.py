import asyncio
import logging
from aiogram import Bot, Dispatcher
from config.config import BOT_TOKEN, DB_URL

# Импорт роутеров
from commands.commands import router as commands_router
from handlers.handlers import router as messages_router
from middleware.auth import auth_middleware
from database.database import init_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Регистрируем роутеры
dp.include_router(commands_router)
dp.include_router(messages_router)

# Подключаем middleware ко всем сообщениям
dp.message.middleware(auth_middleware)


async def main():
    await init_db()
    logging.info("🚀 Бот запускается...")

    try:
        await dp.start_polling(bot)
    except KeyboardInterrupt:
        logging.info("🛑 Бот остановлен пользователем")
    finally:
        await bot.session.close()
        # Закрытие пула БД реализуется в database.py при завершении


if __name__ == "__main__":
    asyncio.run(main())
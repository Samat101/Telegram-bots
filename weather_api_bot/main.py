import asyncio
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from handlers import cmd_start, cmd_help, get_weather_handler, weather_callback

from config import token


bot = Bot(token=token)
dp = Dispatcher()


dp.message.register(cmd_start, Command('start'))
dp.message.register(cmd_help, Command('help'))
dp.message.register(get_weather_handler)
dp.callback_query.register(weather_callback)


async def main():
    await dp.start_polling(bot)



if __name__ == '__main__':
    asyncio.run(main())
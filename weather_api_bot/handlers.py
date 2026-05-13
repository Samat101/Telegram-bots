from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from weather_api import get_weather, format_weather



POPULAR_CITIES = ['Москва', 'Санкт-Петербург', 'Новосибирск', 'Екатеринбург', 'Казань']

async def cmd_start(message: types.Message):
    """
    Обработчик команды /start.
    Отправляет приветственное сообщение с кнопками популярных городов.
    
    Args:
        message: Сообщение от пользователя
    """
    # Создаем клавиатуру с кнопками городов
    builder = InlineKeyboardBuilder()
    for city in POPULAR_CITIES:
        builder.button(text=city, callback_data=f'weather_{city}')
    builder.adjust(2)
    
    await message.answer(
        'Привет! Выбери город или отправь название:',
        reply_markup=builder.as_markup()
    )

async def cmd_help(message: types.Message):
    """
    Обработчик команды /help.
    Отправляет справку по использованию бота.
    
    Args:
        message: Сообщение от пользователя
    """
    await message.answer(
        'Бот показывает погоду.\n'
        '• Нажми кнопку с городом\n'
        '• Или напиши название города'
    )

async def get_weather_handler(message: types.Message):
    """
    Обработчик текстовых сообщений.
    Получает название города и отправляет прогноз погоды.
    """
    city = message.text.strip()
    data = await get_weather(city)
    
    if data.get('cod') != 200:
        await message.answer(f'Город не найден. Проверь название.')
        return
    
    text = format_weather(city, data)
    await message.answer(text)

async def weather_callback(callback: types.CallbackQuery):
    """
    Обработчик нажатий на кнопки с городами.
    
    Args:
        callback: Callback-запрос от нажатия кнопки
    """
    await callback.answer()
    
    city = callback.data.replace('weather_', '')
    data = await get_weather(city)
    
    if data.get('cod') != 200:
        await callback.message.answer(f'Город не найден.')
        return
    
    text = format_weather(city, data)
    await callback.message.edit_text(text)
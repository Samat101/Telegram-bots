import aiohttp
from config import WEATHER_API_KEY




WEATHER_API_URL = 'http://api.openweathermap.org/data/2.5/weather'

async def get_weather(city: str) -> dict:
    """
    Асинхронно получает данные о погоде для указанного города.
    
    Args:
        city: Название города на русском или английском языке
    
    Returns:
        dict: JSON ответ от OpenWeatherMap API с данными о погоде
    """

    params = {
        'q': city,
        'appid': WEATHER_API_KEY,
        'units': 'metric',
        'lang': 'ru'
    }
    

    async with aiohttp.ClientSession() as session:
        async with session.get(WEATHER_API_URL, params=params) as response:
            return await response.json()


def format_weather(city: str, data: dict) -> str:
    """
    Форматирует данные о погоде в читаемое сообщение.
    
    Args:
        city: Название города
        data: Словарь с данными о погоде от API
    
    Returns:
        str: Отформатированное сообщение с информацией о погоде
    """

    weather = data['weather'][0]
    main = data['main']
    

    return (
        f'Погода в {city}:\n'
        f'🌡 Температура: {main["temp"]}°C\n'      
        f'💧 Влажность: {main["humidity"]}%\n'     
        f'💨 Ветер: {data["wind"]["speed"]} м/с\n'  
        f'☁ {weather["description"].capitalize()}'
    )
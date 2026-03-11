# utils.py
from datetime import datetime


def is_admin(user_id: int, admin_ids: list[int]) -> bool:
    """Проверяет, является ли пользователь админом"""
    return user_id in admin_ids


def get_weather_emoji(weather_main: str, is_day: bool = True) -> str:
    """Возвращает эмодзи по типу погоды от OpenWeatherMap"""
    weather_map = {
        "Clear": "☀️" if is_day else "🌙",
        "Clouds": "☁️",
        "Rain": "🌧️",
        "Drizzle": "🌦️",
        "Thunderstorm": "⛈️",
        "Snow": "❄️",
        "Mist": "🌫️",
        "Fog": "🌫️",
        "Haze": "🌫️",
        "Smoke": "🌫️",
        "Dust": "🌫️",
        "Sand": "🌫️",
        "Ash": "🌫️",
        "Squall": "💨",
        "Tornado": "🌪️",
    }
    return weather_map.get(weather_main, "🌤️")  # Фоллбэк
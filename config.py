import os
from datetime import time
from dotenv import load_dotenv

load_dotenv()  # Загружает переменные из .env файла

# Токены — бери из переменных окружения или .env файла
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")

# Настройки по умолчанию
DEFAULT_CITY = "Kazan,RU"
DEFAULT_TIME = time(hour=9, minute=0)

# Таймауты для запросов (сек)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "5"))

# ====== Расширенные настройки ======

# Список городов для поиска (можно расширять)
AVAILABLE_CITIES = {
    "казань": "Kazan,RU",
    "москва": "Moscow,RU",
    "спб": "Saint Petersburg,RU",
    "санкт-петербург": "Saint Petersburg,RU",
    "екатеринбург": "Yekaterinburg,RU",
    "новосибирск": "Novosibirsk,RU",
    "нижний новгород": "Nizhny Novgorod,RU",
    "краснодар": "Krasnodar,RU",
    "самара": "Samara,RU",
    "омск": "Omsk,RU",
}

# Настройки кэширования
CACHE_TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", "600"))
CACHE_TTL_RATES = int(os.getenv("CACHE_TTL_RATES", "1800"))
CACHE_TTL_NEWS = int(os.getenv("CACHE_TTL_NEWS", "900"))

# ====== Админы ======
ADMIN_IDS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
] # ← замени на свой chat_id!
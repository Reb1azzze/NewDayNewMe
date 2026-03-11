# services.py
import json
import logging
from datetime import datetime
from aiohttp import ClientSession, ClientTimeout

from config import (
    OPENWEATHER_API_KEY,
    NEWS_API_KEY,
    REQUEST_TIMEOUT,
    CACHE_TTL_WEATHER,
    CACHE_TTL_RATES,
    CACHE_TTL_NEWS,
)
from cache import api_cache, get_weather_cache_key, get_rates_cache_key, get_news_cache_key
from database import get_user
from utils import get_weather_emoji

logger = logging.getLogger(__name__)


async def fetch_json(session: ClientSession, url: str) -> dict:
    """Универсальный GET-запрос с таймаутом"""
    async with session.get(url, timeout=ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
        resp.raise_for_status()
        text = await resp.text()
        return json.loads(text)


async def get_weather(session: ClientSession, city: str) -> tuple[str, str]:
    """Погода с кэшированием. Возвращает (текст_погоды, эмодзи)"""
    cache_key = get_weather_cache_key(city)
    cached = api_cache.get(cache_key)
    if cached:
        return cached

    try:
        url = (
            f"http://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        )
        data = await fetch_json(session, url)
        if "main" not in data:
            result = ("🌍 Город не найден", "🌍")
        else:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            weather_main = data["weather"][0]["main"]

            # День или ночь?
            sunrise = data["sys"]["sunrise"]
            sunset = data["sys"]["sunset"]
            now = datetime.now().timestamp()
            is_day = sunrise < now < sunset

            emoji = get_weather_emoji(weather_main, is_day)
            result = (f"{desc}, {temp}°C", emoji)
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        result = ("⚠️ Не удалось получить погоду", "⚠️")

    api_cache.set(cache_key, result, ttl=CACHE_TTL_WEATHER)
    return result


async def get_rates(session: ClientSession) -> str:
    """Курсы с кэшированием"""
    cache_key = get_rates_cache_key()
    cached = api_cache.get(cache_key)
    if cached:
        return cached

    try:
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        cbr = await fetch_json(session, url)
        usd = cbr["Valute"]["USD"]["Value"]
        eur = cbr["Valute"]["EUR"]["Value"]
        result = f"🇺🇸 USD: {usd:.2f} ₽\n🇪🇺 EUR: {eur:.2f} ₽"
    except Exception as e:
        logger.error(f"Rates error: {e}")
        result = "⚠️ Не удалось получить курсы"

    api_cache.set(cache_key, result, ttl=CACHE_TTL_RATES)
    return result


async def get_news(session: ClientSession) -> str:
    """Новости с кэшированием"""
    cache_key = get_news_cache_key()
    cached = api_cache.get(cache_key)
    if cached:
        return cached

    try:
        url = (
            f"https://newsapi.org/v2/everything?"
            f"q=Россия&language=ru&sortBy=publishedAt&pageSize=1"
            f"&apiKey={NEWS_API_KEY}"
        )
        data = await fetch_json(session, url)

        if data.get("status") == "error":
            logger.warning(f"NewsAPI: {data.get('message')}")
            result = "📰 Новости временно недоступны"
        elif not data.get("articles"):
            result = "📰 Новостей пока нет"
        else:
            article = data["articles"][0]
            title = article.get("title", "Без заголовка")
            url = article.get("url", "#")
            result = f"{title}\n🔗 {url}"
    except Exception as e:
        logger.error(f"News error: {e}")
        result = "📰 Не удалось загрузить новости"

    api_cache.set(cache_key, result, ttl=CACHE_TTL_NEWS)
    return result


async def build_digest(session: ClientSession, chat_id: int, default_city: str) -> str:
    """Собирает дайджест для пользователя"""
    settings = get_user(chat_id)
    if not settings:
        settings = {"city": default_city, "send_time": "09:00"}

    city = settings["city"]
    city_name = city.split(",")[0]

    weather_text, weather_emoji = await get_weather(session, city)
    rates = await get_rates(session)
    news = await get_news(session)
    today = datetime.now().strftime("%d.%m.%Y")

    return (
        f"🗓️ Сегодня: {today}\n\n"
        f"{weather_emoji} Погода в {city_name}: {weather_text}\n\n"
        f"💰 Курсы валют:\n{rates}\n\n"
        f"📰 Топ новость:\n{news}"
    )


async def send_digest(session: ClientSession, bot, chat_id: int, default_city: str):
    """Отправляет дайджест пользователю"""
    try:
        text = await build_digest(session, chat_id, default_city)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info(f"Digest sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send digest to {chat_id}: {e}")
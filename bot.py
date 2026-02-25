import asyncio
import logging
import sys
import json
import re
from datetime import datetime, time as dt_time
from typing import Optional
from logging.handlers import RotatingFileHandler
from pathlib import Path
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, CallbackQuery, ForceReply, BotCommand, BotCommandScopeDefault, \
    BotCommandScopeChat, BotCommandScopeAllPrivateChats
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import ClientSession, ClientTimeout
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import (
    TELEGRAM_TOKEN,
    OPENWEATHER_API_KEY,
    NEWS_API_KEY,
    DEFAULT_CITY,
    DEFAULT_TIME,
    REQUEST_TIMEOUT,
    AVAILABLE_CITIES,
    CACHE_TTL_WEATHER,
    CACHE_TTL_RATES,
    CACHE_TTL_NEWS,
    ADMIN_IDS,
)
from database import (
    init_db, get_user, save_user, create_user_if_not_exists,
    get_all_users, get_stats, search_users, update_user_field
)
from cache import api_cache, get_weather_cache_key, get_rates_cache_key, get_news_cache_key

# Команды для всех
USER_COMMANDS = [
    BotCommand(command="start", description="🚀 Запустить бота"),
    BotCommand(command="my_settings", description="⚙️ Мои настройки"),
]

# Команды для админов
ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand(command="stats", description="📊 Статистика"),
    BotCommand(command="broadcast", description="📢 Рассылка"),
    BotCommand(command="user_info", description="👤 Инфо о пользователе"),
    BotCommand(command="clear_cache", description="🧹 Очистить кэш"),
]

# ====== Логирование ======
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

file_handler = RotatingFileHandler(
    LOG_DIR / "bot.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8"
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
))

try:
    import colorlog

    console_handler = colorlog.StreamHandler()
    console_handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        log_colors={
            "DEBUG": "cyan", "INFO": "green", "WARNING": "yellow",
            "ERROR": "red", "CRITICAL": "bold_red",
        }
    ))
except ImportError:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
console_handler.setLevel(logging.INFO)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, console_handler])
logger = logging.getLogger(__name__)

# ====== Глобальные объекты ======
storage = MemoryStorage()
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
http_session: Optional[ClientSession] = None


# ====== FSM для поиска города ======
class CitySearch(StatesGroup):
    waiting_for_city = State()


# ====== API функции с кэшированием ======
async def fetch_json(url: str) -> dict:
    async with http_session.get(url, timeout=ClientTimeout(total=REQUEST_TIMEOUT)) as resp:
        resp.raise_for_status()
        text = await resp.text()
        return json.loads(text)


async def get_weather(city: str) -> str:
    """Погода с кэшированием"""
    cache_key = get_weather_cache_key(city)

    # Пробуем получить из кэша
    cached = api_cache.get(cache_key)
    if cached:
        return cached

    # Запрашиваем API
    try:
        url = (
            f"http://api.openweathermap.org/data/2.5/weather"
            f"?q={city}&appid={OPENWEATHER_API_KEY}&units=metric&lang=ru"
        )
        data = await fetch_json(url)
        if "main" not in data:
            result = "🌍 Город не найден"
        else:
            temp = data["main"]["temp"]
            desc = data["weather"][0]["description"].capitalize()
            result = f"{desc}, {temp}°C"
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        result = "⚠️ Не удалось получить погоду"

    # Сохраняем в кэш
    api_cache.set(cache_key, result, ttl=CACHE_TTL_WEATHER)
    return result


async def get_rates() -> str:
    """Курсы с кэшированием"""
    cache_key = get_rates_cache_key()

    cached = api_cache.get(cache_key)
    if cached:
        return cached

    try:
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        cbr = await fetch_json(url)
        usd = cbr["Valute"]["USD"]["Value"]
        eur = cbr["Valute"]["EUR"]["Value"]
        result = f"🇺🇸 USD: {usd:.2f} ₽\n🇪🇺 EUR: {eur:.2f} ₽"
    except Exception as e:
        logger.error(f"Rates error: {e}")
        result = "⚠️ Не удалось получить курсы"

    api_cache.set(cache_key, result, ttl=CACHE_TTL_RATES)
    return result


async def get_news() -> str:
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
        data = await fetch_json(url)

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


# ====== Формирование сообщения ======
async def build_digest(chat_id: int) -> str:
    settings = get_user(chat_id)
    if not settings:
        settings = {"city": DEFAULT_CITY, "send_time": "09:00"}

    city = settings["city"]
    city_name = city.split(",")[0]

    weather = await get_weather(city)
    rates = await get_rates()
    news = await get_news()
    today = datetime.now().strftime("%d.%m.%Y")

    return (
        f"📅 Сегодня: {today}\n\n"
        f"🌤 Погода в {city_name}: {weather}\n\n"
        f"💰 Курсы валют:\n{rates}\n\n"
        f"📰 Топ новость:\n{news}"
    )


async def send_digest(chat_id: int):
    try:
        text = await build_digest(chat_id)
        await bot.send_message(chat_id=chat_id, text=text)
        logger.info(f"Digest sent to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send digest to {chat_id}: {e}")


# ====== Клавиатуры ======
def main_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌍 Изменить город", callback_data="settings:city"))
    builder.row(InlineKeyboardButton(text="⏰ Изменить время", callback_data="settings:time"))
    builder.row(InlineKeyboardButton(text="🔄 Получить сейчас", callback_data="action:now"))
    return builder.as_markup()


def city_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    # Популярные города
    popular = [("Казань", "Kazan,RU"), ("Москва", "Moscow,RU"),
               ("СПб", "Saint Petersburg,RU"), ("Екб", "Yekaterinburg,RU")]
    for name, code in popular:
        builder.button(text=name, callback_data=f"city:{code}")
    builder.button(text="🔍 Поиск города...", callback_data="city:search")
    builder.button(text="🔙 Назад", callback_data="settings:back")
    builder.adjust(2)
    return builder.as_markup()


def time_keyboard() -> types.InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    times = ["06:00", "09:00", "12:00", "18:00", "21:00", "16:37"]
    for t in times:
        builder.button(text=t, callback_data=f"time:{t}")
    builder.button(text="🔙 Назад", callback_data="settings:back")
    builder.adjust(3)
    return builder.as_markup()


# ====== Хендлеры ======
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    chat_id = message.chat.id
    create_user_if_not_exists(chat_id, DEFAULT_CITY, "09:00")

    remove_scheduled_job(chat_id)
    settings = get_user(chat_id)
    create_scheduled_job(chat_id, settings["send_time"])

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я буду присылать тебе дайджест: погода, курсы и новости.\n"
        f"Настрой меня под себя:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"/start from {chat_id}")


@dp.message(Command("my_settings"))
async def cmd_my_settings(message: types.Message):
    chat_id = message.chat.id
    settings = get_user(chat_id)

    if not settings:
        await message.answer("⚠️ Ты ещё не настроил бота. Напиши /start")
        return

    city_name = settings["city"].split(",")[0]
    send_time = settings["send_time"]

    await message.answer(
        f"⚙️ Твои настройки:\n\n"
        f"🌍 Город: {city_name}\n"
        f"⏰ Время: {send_time}\n\n"
        f"Нажми на кнопки, чтобы изменить:",
        reply_markup=main_keyboard(),
    )


# Поиск города через текст
@dp.message(CitySearch.waiting_for_city)
async def process_city_search(message: types.Message, state: FSMContext):
    city_input = message.text.strip().lower()
    chat_id = message.chat.id

    # Проверяем в списке AVAILABLE_CITIES
    city_code = AVAILABLE_CITIES.get(city_input)

    if city_code:
        # Нашли в списке — сохраняем
        settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
        settings["city"] = city_code
        save_user(chat_id, settings["city"], settings["send_time"])

        remove_scheduled_job(chat_id)
        create_scheduled_job(chat_id, settings["send_time"])

        city_name = city_code.split(",")[0]
        await message.answer(
            f"✅ Город установлен: {city_name}\n\n⚙️ Настройки:",
            reply_markup=main_keyboard(),
        )
        logger.info(f"City set via search: {city_name} for {chat_id}")
    else:
        # Не нашли — предлагаем варианты
        matches = [name for name in AVAILABLE_CITIES if city_input in name]
        if matches:
            keyboard = InlineKeyboardBuilder()
            for match in matches[:5]:  # Показываем до 5 совпадений
                keyboard.button(
                    text=match.capitalize(),
                    callback_data=f"city:{AVAILABLE_CITIES[match]}"
                )
            keyboard.adjust(2)
            await message.answer(
                f"🤔 Возможно, ты имел в виду:\n\n"
                f"{' / '.join(matches)}\n\n"
                f"Или введи название точнее:",
                reply_markup=keyboard.as_markup(),
            )
        else:
            # Совсем не нашли — пробуем отправить как есть (для OpenWeather)
            # Форматируем: "новосибирск" → "Novosibirsk,RU"
            city_formatted = city_input.title().replace(" ", "") + ",RU"

            settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
            settings["city"] = city_formatted
            save_user(chat_id, settings["city"], settings["send_time"])

            remove_scheduled_job(chat_id)
            create_scheduled_job(chat_id, settings["send_time"])

            await message.answer(
                f"✅ Принято: {city_input.title()}\n"
                f"⚠️ Если погода не отображается — проверь название города\n\n"
                f"⚙️ Настройки:",
                reply_markup=main_keyboard(),
            )
            logger.info(f"City set via free input: {city_formatted} for {chat_id}")

    await state.clear()


@dp.callback_query(F.data == "action:now")
async def action_now(callback: CallbackQuery):
    await callback.answer("🔄 Обновляю...")
    chat_id = callback.message.chat.id
    text = await build_digest(chat_id)
    await callback.message.answer(text)


@dp.callback_query(F.data == "settings:city")
async def settings_city(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "🌍 Выбери город:",
        reply_markup=city_keyboard(),
    )


@dp.callback_query(F.data == "city:search")
async def start_city_search(callback: CallbackQuery, state: FSMContext):
    """Начать поиск города"""
    await callback.answer()
    await callback.message.edit_text(
        "🔍 Введите название города:\n\n"
        "Примеры: Казань, Москва, Новосибирск",
    )

    await state.set_state(CitySearch.waiting_for_city)
    await callback.message.answer(
        "✍️ Напиши название города:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@dp.callback_query(F.data == "settings:time")
async def settings_time(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⏰ Во сколько присылать дайджест?",
        reply_markup=time_keyboard(),
    )


@dp.callback_query(F.data == "settings:back")
async def settings_back(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ Настройки дайджеста:",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data.startswith("city:"))
async def set_city(callback: CallbackQuery):
    city_code = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id

    if city_code == "search":  # Обработано выше
        return

    settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
    settings["city"] = city_code
    save_user(chat_id, settings["city"], settings["send_time"])

    remove_scheduled_job(chat_id)
    create_scheduled_job(chat_id, settings["send_time"])

    city_name = city_code.split(",")[0]
    await callback.answer(f"✅ Город: {city_name}")
    await callback.message.edit_text(
        f"✅ Выбран город: {city_name}\n\n⚙️ Настройки:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"City set: {city_name} for {chat_id}")


@dp.callback_query(F.data.startswith("time:"))
async def set_time(callback: CallbackQuery):
    time_str = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id

    settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
    settings["send_time"] = time_str
    save_user(chat_id, settings["city"], settings["send_time"])

    remove_scheduled_job(chat_id)
    create_scheduled_job(chat_id, time_str)

    await callback.answer(f"✅ Время: {time_str}")
    await callback.message.edit_text(
        f"✅ Дайджест в {time_str}\n\n⚙️ Настройки:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"Time set: {time_str} for {chat_id}")


# 🔥 АДМИН-КОМАНДЫ
def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    stats = get_stats()
    cache_stats = api_cache.get_stats()

    text = f"📊 Статистика бота:\n\n"
    text += f"👥 Пользователей: {stats['total_users']}\n"
    text += f"🆕 Новых сегодня: {stats['new_today']}\n\n"

    if stats['top_cities']:
        text += "🌍 Топ городов:\n"
        for c in stats['top_cities'][:3]:
            city = c['city'].split(',')[0]
            text += f"  • {city}: {c['count']}\n"
        text += "\n"

    text += f"💾 Кэш: {cache_stats['valid']}/{cache_stats['total']} записей валидны\n"

    await message.answer(text)
    logger.info(f"/stats by admin {message.from_user.id}")


@dp.message(Command("broadcast"))
async def cmd_broadcast(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    # Получаем текст после команды
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("⚠️ Использование: /broadcast Текст сообщения")
        return

    # Отправляем всем пользователям
    users = get_all_users()
    success = 0
    failed = 0

    status_msg = await message.answer(f"📤 Рассылка: 0/{len(users)}...")

    for user in users:
        try:
            await bot.send_message(chat_id=user["chat_id"], text=text)
            success += 1
            await asyncio.sleep(0.05)  # Небольшая пауза
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {user['chat_id']}: {e}")

        # Обновляем статус каждые 10 сообщений
        if success % 10 == 0:
            await status_msg.edit_text(f"📤 Рассылка: {success}/{len(users)}...")

    await status_msg.edit_text(
        f"✅ Рассылка завершена:\n"
        f"📬 Доставлено: {success}\n"
        f"❌ Ошибок: {failed}"
    )
    logger.info(f"Broadcast sent: {success}/{len(users)} by admin {message.from_user.id}")


@dp.message(Command("user_info"))
async def cmd_user_info(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    # Получаем chat_id из аргумента
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Использование: /user_info <chat_id>")
        return

    try:
        chat_id = int(args[1])
    except ValueError:
        await message.answer("⚠️ chat_id должен быть числом")
        return

    user = get_user(chat_id)
    if not user:
        await message.answer(f"❌ Пользователь {chat_id} не найден в БД")
        return

    city = user["city"].split(",")[0]
    text = (
        f"👤 Информация о пользователе:\n\n"
        f"🆔 Chat ID: {chat_id}\n"
        f"🌍 Город: {city}\n"
        f"⏰ Время: {user['send_time']}\n"
        f"💾 В базе с: {datetime.now().strftime('%d.%m.%Y')}"
    )
    await message.answer(text)


@dp.message(Command("clear_cache"))
async def cmd_clear_cache(message: types.Message):
    if not is_admin(message.from_user.id):
        return

    count = api_cache.clear()
    await message.answer(f"🧹 Кэш очищен: {count} записей удалено")
    logger.info(f"Cache cleared by admin {message.from_user.id}")


# ====== Планировщик ======
def create_scheduled_job(chat_id: int, send_time_str: str):
    h, m = map(int, send_time_str.split(":"))
    send_time = dt_time(hour=h, minute=m)

    job_id = f"digest_{chat_id}"
    scheduler.add_job(
        send_digest,
        trigger=CronTrigger(hour=send_time.hour, minute=send_time.minute),
        args=[chat_id],
        id=job_id,
        replace_existing=True,
        name=job_id,
    )
    logger.info(f"📅 Scheduled job {job_id} for {send_time_str}")


def remove_scheduled_job(chat_id: int):
    job_id = f"digest_{chat_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"🗑️ Removed job {job_id}")


# ====== Запуск ======
async def on_startup():
    """Инициализация при старте"""
    global http_session

    # Команды для всех пользователей
    await bot.set_my_commands(
        commands=USER_COMMANDS,
        scope=BotCommandScopeAllPrivateChats()  # Все личные чаты
    )

    # Дополнительные команды для админов
    for admin_id in ADMIN_IDS:
        await bot.set_my_commands(
            commands=ADMIN_COMMANDS,
            scope=BotCommandScopeChat(chat_id=admin_id)  # Только для админа
        )

    logger.info("📋 Commands registered for users and admins")

    init_db()
    http_session = ClientSession()
    scheduler.start()

    # Восстанавливаем задачи из БД
    for user in get_all_users():
        create_scheduled_job(user["chat_id"], user["send_time"])

    logger.info("Bot started ✅")


async def on_shutdown():
    if http_session:
        await http_session.close()
    scheduler.shutdown()
    await bot.session.close()
    logger.info("Bot stopped 👋")


async def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Stopped by user")
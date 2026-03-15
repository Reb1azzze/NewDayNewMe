#bot.py
import asyncio
import logging
import sys

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
from functools import partial
from migrations import run_migrations

from config import (
    TELEGRAM_TOKEN,
    DEFAULT_CITY,
    ADMIN_IDS,
)
from database import (
    init_db, get_all_users,
)
from services import send_digest
from scheduler import create_scheduled_job, remove_scheduled_job
from handlers import (
    cmd_start, cmd_my_settings, CitySearch, TimeSearch,
    settings_city, settings_time, settings_back,
    start_city_search, set_city, set_time,
    process_city_search, process_time_input,
    action_now,
    cmd_stats, cmd_broadcast, cmd_user_info, cmd_clear_cache
)

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

# ====== Обёртки для хендлеров из handlers.py ======
async def cmd_start_wrapper(message: types.Message):
    await cmd_start(message, scheduler, create_scheduled_job, remove_scheduled_job, DEFAULT_CITY)

async def set_city_wrapper(callback: types.CallbackQuery):
    await set_city(callback, scheduler, create_scheduled_job, remove_scheduled_job)

async def set_time_wrapper(callback: types.CallbackQuery):
    await set_time(callback, scheduler, create_scheduled_job, remove_scheduled_job)

async def process_city_search_wrapper(message: types.Message, state: FSMContext):
    await process_city_search(message, state, scheduler, create_scheduled_job, remove_scheduled_job)

async def action_now_wrapper(callback: types.CallbackQuery):
    await action_now(callback, http_session, DEFAULT_CITY)

async def cmd_stats_wrapper(message: types.Message):
    await cmd_stats(message, ADMIN_IDS)

async def cmd_broadcast_wrapper(message: types.Message):
    await cmd_broadcast(message, bot, ADMIN_IDS)

async def cmd_user_info_wrapper(message: types.Message):
    await cmd_user_info(message, ADMIN_IDS)

async def cmd_clear_cache_wrapper(message: types.Message):
    await cmd_clear_cache(message, ADMIN_IDS)

async def process_time_input_wrapper(message: types.Message, state: FSMContext):
    await process_time_input(message, state, scheduler, create_scheduled_job, remove_scheduled_job)

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

# ====== Регистрация хендлеров ======
# Команды
dp.message(CommandStart())(cmd_start_wrapper)
dp.message(Command("my_settings"))(cmd_my_settings)

# Callbacks: настройки
dp.callback_query(F.data == "settings:city")(settings_city)
dp.callback_query(F.data == "settings:time")(settings_time)
dp.callback_query(F.data == "settings:back")(settings_back)
dp.callback_query(F.data == "city:search")(start_city_search)
dp.callback_query(F.data.startswith("city:"))(set_city_wrapper)
dp.callback_query(F.data.startswith("time:"))(set_time_wrapper)
dp.callback_query(F.data == "action:now")(action_now_wrapper)

# FSM: поиск города
dp.message(CitySearch.waiting_for_city)(process_city_search_wrapper)
dp.message(TimeSearch.waiting_for_time)(process_time_input_wrapper)

# Поиск города через текст

dp.message(Command("stats"))(cmd_stats_wrapper)
dp.message(Command("broadcast"))(cmd_broadcast_wrapper)
dp.message(Command("user_info"))(cmd_user_info_wrapper)
dp.message(Command("clear_cache"))(cmd_clear_cache_wrapper)


# ====== Планировщик ======
def create_scheduled_job(chat_id: int, send_time_str: str):
    """Обёртка для scheduler.create_scheduled_job"""
    # Создаём «обёртку» с заранее переданными session, bot, default_city
    digest_func = partial(
        send_digest,
        http_session,  # session
        bot,  # bot
        default_city=DEFAULT_CITY
    )

    # Вызываем функцию из scheduler.py
    from scheduler import create_scheduled_job as create_job
    create_job(scheduler, digest_func, chat_id, send_time_str)


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
    run_migrations()
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
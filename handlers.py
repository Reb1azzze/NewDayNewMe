# handlers.py
import logging
import asyncio
from datetime import datetime

from aiogram import F, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DEFAULT_CITY, AVAILABLE_CITIES, ADMIN_IDS  # ← ADMIN_IDS тоже нужен
from database import (
    get_user,
    save_user,
    create_user_if_not_exists,
    get_all_users,
    get_stats,
)
from cache import api_cache
from keyboards import main_keyboard, city_keyboard, time_keyboard
from utils import is_admin

logger = logging.getLogger(__name__)

# ====== FSM ======
class CitySearch(StatesGroup):
    waiting_for_city = State()


# ====== Команды ======
async def cmd_start(
        message: types.Message,
        scheduler,
        create_job_func,
        remove_job_func,
        default_city: str = DEFAULT_CITY
):
    """Обработка /start"""
    chat_id = message.chat.id
    create_user_if_not_exists(chat_id, default_city, "09:00")

    remove_job_func(chat_id)
    settings = get_user(chat_id)
    create_job_func(chat_id, settings["send_time"])

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}!\n\n"
        f"Я буду присылать тебе дайджест: погода, курсы и новости.\n"
        f"Настрой меня под себя:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"/start from {chat_id}")


async def cmd_my_settings(message: types.Message):
    """Показать настройки пользователя"""
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

# ====== Callbacks: настройки ======
async def settings_city(callback: types.CallbackQuery):
    """Показать меню выбора города"""
    await callback.answer()
    await callback.message.edit_text(
        "🌍 Выбери город:",
        reply_markup=city_keyboard(),
    )


async def settings_time(callback: types.CallbackQuery):
    """Показать меню выбора времени"""
    await callback.answer()
    await callback.message.edit_text(
        "⏰ Во сколько присылать дайджест?",
        reply_markup=time_keyboard(),
    )


async def settings_back(callback: types.CallbackQuery):
    """Возврат в главное меню"""
    await callback.answer()
    await callback.message.edit_text(
        "⚙️ Настройки дайджеста:",
        reply_markup=main_keyboard(),
    )


async def start_city_search(callback: types.CallbackQuery, state: FSMContext):
    """Начать поиск города"""
    await callback.answer()
    await callback.message.edit_text(
        "🔍 Введите название города:\n\nПримеры: Казань, Москва, Новосибирск"
    )
    await state.set_state(CitySearch.waiting_for_city)
    await callback.message.answer(
        "✍️ Напиши название города:",
        reply_markup=types.ReplyKeyboardRemove()
    )


async def set_city(
    callback: types.CallbackQuery,
    scheduler,
    create_job_func,
    remove_job_func
):
    """Установить выбранный город"""
    city_code = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id

    if city_code == "search":
        return

    settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
    settings["city"] = city_code
    save_user(chat_id, settings["city"], settings["send_time"])

    remove_job_func(chat_id)
    create_job_func(chat_id, settings["send_time"])

    city_name = city_code.split(",")[0]
    await callback.answer(f"✅ Город: {city_name}")
    await callback.message.edit_text(
        f"✅ Выбран город: {city_name}\n\n⚙️ Настройки:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"City set: {city_name} for {chat_id}")


async def set_time(
    callback: types.CallbackQuery,
    scheduler,
    create_job_func,
    remove_job_func
):
    """Установить выбранное время"""
    time_str = callback.data.split(":", 1)[1]
    chat_id = callback.message.chat.id

    settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
    settings["send_time"] = time_str
    save_user(chat_id, settings["city"], settings["send_time"])

    remove_job_func(chat_id)
    create_job_func(chat_id, time_str)

    await callback.answer(f"✅ Время: {time_str}")
    await callback.message.edit_text(
        f"✅ Дайджест в {time_str}\n\n⚙️ Настройки:",
        reply_markup=main_keyboard(),
    )
    logger.info(f"Time set: {time_str} for {chat_id}")


async def process_city_search(
    message: types.Message,
    state: FSMContext,
    scheduler,
    create_job_func,
    remove_job_func
):
    """Обработать ввод города пользователем"""
    city_input = message.text.strip().lower()
    chat_id = message.chat.id

    city_code = AVAILABLE_CITIES.get(city_input)

    if city_code:
        settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
        settings["city"] = city_code
        save_user(chat_id, settings["city"], settings["send_time"])

        remove_job_func(chat_id)
        create_job_func(chat_id, settings["send_time"])

        city_name = city_code.split(",")[0]
        await message.answer(
            f"✅ Город установлен: {city_name}\n\n⚙️ Настройки:",
            reply_markup=main_keyboard(),
        )
        logger.info(f"City set via search: {city_name} for {chat_id}")
    else:
        matches = [name for name in AVAILABLE_CITIES if city_input in name]
        if matches:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            keyboard = InlineKeyboardBuilder()
            for match in matches[:5]:
                keyboard.button(text=match.capitalize(), callback_data=f"city:{AVAILABLE_CITIES[match]}")
            keyboard.adjust(2)
            await message.answer(
                f"🤔 Возможно, ты имел в виду:\n\n{' / '.join(matches)}\n\nИли введи название точнее:",
                reply_markup=keyboard.as_markup(),
            )
        else:
            city_formatted = city_input.title().replace(" ", "") + ",RU"
            settings = get_user(chat_id) or {"city": DEFAULT_CITY, "send_time": "09:00"}
            settings["city"] = city_formatted
            save_user(chat_id, settings["city"], settings["send_time"])

            remove_job_func(chat_id)
            create_job_func(chat_id, settings["send_time"])

            await message.answer(
                f"✅ Принято: {city_input.title()}\n⚠️ Если погода не отображается — проверь название города\n\n⚙️ Настройки:",
                reply_markup=main_keyboard(),
            )
            logger.info(f"City set via free input: {city_formatted} for {chat_id}")

    await state.clear()


async def action_now(callback: types.CallbackQuery, session, default_city: str):
    """Мгновенная отправка дайджеста"""
    from services import build_digest  # локальный импорт, чтобы не было цикла
    await callback.answer("🔄 Обновляю...")
    chat_id = callback.message.chat.id
    text = await build_digest(session, chat_id, default_city)
    await callback.message.answer(text)

# ====== Админ-команды ======
async def cmd_stats(message: types.Message, admin_ids: list[int]):
    """Показать статистику бота"""
    if not is_admin(message.from_user.id, admin_ids):
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


async def cmd_broadcast(message: types.Message, bot, admin_ids: list[int]):
    """Рассылка сообщения всем пользователям"""
    if not is_admin(message.from_user.id, admin_ids):
        return

    text = message.text.replace("/broadcast", "").strip()
    if not text:
        await message.answer("⚠️ Использование: /broadcast Текст сообщения")
        return

    users = get_all_users()
    success = 0
    failed = 0

    status_msg = await message.answer(f"📤 Рассылка: 0/{len(users)}...")

    for user in users:
        try:
            await bot.send_message(chat_id=user["chat_id"], text=text)
            success += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            failed += 1
            logger.error(f"Broadcast failed for {user['chat_id']}: {e}")

        if success % 10 == 0:
            await status_msg.edit_text(f"📤 Рассылка: {success}/{len(users)}...")

    await status_msg.edit_text(
        f"✅ Рассылка завершена:\n📬 Доставлено: {success}\n❌ Ошибок: {failed}"
    )
    logger.info(f"Broadcast sent: {success}/{len(users)} by admin {message.from_user.id}")


async def cmd_user_info(message: types.Message, admin_ids: list[int]):
    """Инфо о пользователе"""
    if not is_admin(message.from_user.id, admin_ids):
        return

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


async def cmd_clear_cache(message: types.Message, admin_ids: list[int]):
    """Очистить кэш"""
    if not is_admin(message.from_user.id, admin_ids):
        return

    count = api_cache.clear()
    await message.answer(f"🧹 Кэш очищен: {count} записей удалено")
    logger.info(f"Cache cleared by admin {message.from_user.id}")
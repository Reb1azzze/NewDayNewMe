# keyboards.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_keyboard() -> InlineKeyboardMarkup:
    """Главное меню с настройками"""
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🌍 Изменить город", callback_data="settings:city"))
    builder.row(InlineKeyboardButton(text="⏰ Изменить время", callback_data="settings:time"))
    builder.row(InlineKeyboardButton(text="🔄 Получить сейчас", callback_data="action:now"))
    return builder.as_markup()


def city_keyboard() -> InlineKeyboardMarkup:
    """Выбор города"""
    builder = InlineKeyboardBuilder()
    popular = [
        ("Казань", "Kazan,RU"),
        ("Москва", "Moscow,RU"),
        ("СПб", "Saint Petersburg,RU"),
        ("Екб", "Yekaterinburg,RU"),
    ]
    for name, code in popular:
        builder.button(text=name, callback_data=f"city:{code}")
    builder.button(text="🔍 Поиск города...", callback_data="city:search")
    builder.button(text="🔙 Назад", callback_data="settings:back")
    builder.adjust(2)
    return builder.as_markup()


def time_keyboard() -> InlineKeyboardMarkup:
    """Выбор времени"""
    builder = InlineKeyboardBuilder()
    times = ["06:00", "09:00", "12:00", "18:00", "21:00", "15:06"]
    for t in times:
        builder.button(text=t, callback_data=f"time:{t}")
    builder.button(text="🔙 Назад", callback_data="settings:back")
    builder.adjust(3)
    return builder.as_markup()
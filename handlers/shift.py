"""
Меню оператора. Вся сдача смены происходит в Mini App —
бот здесь просто открывает его и дальше принимает уже готовый
отчёт через HTTP API (см. api.py), не через диалог в чате.
"""
from aiogram import Router
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)

import storage
from config import OPERATOR_WEBAPP_URL
from locales import t

router = Router()


def operator_keyboard(lang: str) -> ReplyKeyboardMarkup:
    buttons = []
    if OPERATOR_WEBAPP_URL:
        buttons.append([KeyboardButton(
            text=t("start_shift_btn", lang),
            web_app=WebAppInfo(url=OPERATOR_WEBAPP_URL),
        )])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def send_operator_menu(message: Message):
    lang = storage.get_operator_lang(message.from_user.id)
    await message.answer(t("operator_menu", lang), reply_markup=operator_keyboard(lang))

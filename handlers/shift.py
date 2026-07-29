"""
Меню оператора. Вся сдача смены происходит в Mini App —
бот здесь просто открывает его (инлайн-кнопкой в сообщении) и дальше
принимает уже готовый отчёт через HTTP API (см. api.py), не через
диалог в чате.
"""
from aiogram import Router
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo,
)

import storage
from config import OPERATOR_WEBAPP_URL
from locales import t

router = Router()


def operator_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = []
    if OPERATOR_WEBAPP_URL:
        buttons.append([InlineKeyboardButton(
            text=t("start_shift_btn", lang),
            web_app=WebAppInfo(url=OPERATOR_WEBAPP_URL),
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def send_operator_menu(message: Message, lang: str = None):
    tg_id = message.from_user.id if message.from_user else None
    if lang is None:
        lang = storage.get_lang(tg_id) if tg_id else "ru"
    await message.answer(t("operator_menu", lang), reply_markup=operator_keyboard(lang))

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
)

import storage
from config import OWNER_WEBAPP_URL
from locales import t
from handlers.registration import approval_keyboard

router = Router()


def owner_keyboard(lang):
    buttons = []
    if OWNER_WEBAPP_URL:
        buttons.append([KeyboardButton(
            text=t("owner_menu", lang),
            web_app=WebAppInfo(url=OWNER_WEBAPP_URL),
        )])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


async def send_owner_menu(message: Message, lang=None):
    tg_id = message.from_user.id if message.from_user else None
    if lang is None:
        lang = storage.get_lang(tg_id) if tg_id else "ru"
    await message.answer(t("owner_menu", lang), reply_markup=owner_keyboard(lang))


@router.message(Command("pending"))
async def cmd_pending(message: Message):
    from config import OWNER_IDS
    if message.from_user.id not in OWNER_IDS:
        return

    lang = storage.get_lang(message.from_user.id, default="ru")
    pending = storage.get_pending()
    if not pending:
        await message.answer(t("pending_list_empty", lang))
        return

    for tg_id, p in pending.items():
        await message.answer(
            t("pending_item", lang, name=p["name"], phone=p["phone"], tg_id=tg_id),
            reply_markup=approval_keyboard(int(tg_id)),
        )

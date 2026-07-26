"""
Регистрация операторов:
- Первое, что видит новый человек — выбор языка (RU/UZ).
- Дальше — просим поделиться контактом и именем -> заявка уходит владельцу.
- Пока не одобрен — бот ничего больше не отвечает и не пускает дальше.
- Владелец одобряет/отклоняет через инлайн-кнопки.
- Язык можно сменить в любой момент командой /lang.
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton,
)

import storage
from config import OWNER_IDS
from locales import t

router = Router()


class Registration(StatesGroup):
    waiting_contact = State()
    waiting_name = State()


def lang_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Русский", callback_data="setlang:ru"),
        InlineKeyboardButton(text="O'zbekcha", callback_data="setlang:uz"),
    ]])


def contact_keyboard(lang):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("share_contact_btn", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def approval_keyboard(tg_id):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Odobrit / Tasdiqlash", callback_data="approve:" + str(tg_id)),
        InlineKeyboardButton(text="Otklonit / Rad etish", callback_data="reject:" + str(tg_id)),
    ]])


async def _continue_after_language(message, state, tg_id, lang):
    if tg_id in OWNER_IDS:
        from handlers.owner import send_owner_menu
        await send_owner_menu(message, lang)
        return

    if storage.is_operator(tg_id):
        from handlers.shift import send_operator_menu
        await send_operator_menu(message, lang)
        return

    if storage.is_pending(tg_id):
        await message.answer(t("already_pending", lang))
        return

    await state.set_state(Registration.waiting_contact)
    await message.answer(t("welcome_unknown", lang), reply_markup=contact_keyboard(lang))


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    tg_id = message.from_user.id
    await state.clear()

    known_lang = storage.get_lang(tg_id, default=None)
    if known_lang is None:
        await message.answer(t("choose_lang", "ru"), reply_markup=lang_keyboard())
        return

    await _continue_after_language(message, state, tg_id, known_lang)


@router.message(Command("lang"))
async def cmd_lang(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(t("choose_lang", "ru"), reply_markup=lang_keyboard())


@router.callback_query(F.data.startswith("setlang:"))
async def cb_set_lang(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split(":")[1]
    tg_id = callback.from_user.id
    storage.set_lang(tg_id, lang)

    await callback.message.edit_text(t("lang_set", lang))
    await callback.answer()
    await _continue_after_language(callback.message, state, tg_id, lang)


@router.message(Registration.waiting_contact, F.contact)
async def got_contact(message: Message, state: FSMContext):
    lang = storage.get_lang(message.from_user.id)
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await state.set_state(Registration.waiting_name)
    await message.answer(t("ask_name", lang), reply_markup=ReplyKeyboardRemove())


@router.message(Registration.waiting_name, F.text)
async def got_name(message: Message, state: FSMContext, bot: Bot):
    tg_id = message.from_user.id
    lang = storage.get_lang(tg_id)
    data = await state.get_data()
    phone = data.get("phone", "-")
    name = message.text.strip()

    storage.add_pending(tg_id, name, phone)
    await state.clear()
    await message.answer(t("request_sent", lang))

    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(
                owner_id,
                t("pending_item", "ru", name=name, phone=phone, tg_id=tg_id),
                reply_markup=approval_keyboard(tg_id),
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("Nedostupno", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[1])
    pending = storage.get_pending().get(str(tg_id))
    if not pending:
        await callback.answer("Zayavka uzhe obrabotana")
        return

    operator_lang = storage.get_lang(tg_id, default="ru")
    storage.add_operator(tg_id, pending["name"], pending["phone"], lang=operator_lang)
    storage.remove_pending(tg_id)

    await callback.message.edit_text(callback.message.text + "\n\nOdobreno")
    await callback.answer("Operator dobavlen")
    try:
        await bot.send_message(tg_id, t("approved_notify", operator_lang))
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("Nedostupno", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[1])
    pending = storage.get_pending().get(str(tg_id))
    if not pending:
        await callback.answer("Zayavka uzhe obrabotana")
        return

    lang = storage.get_lang(tg_id, default="ru")
    storage.remove_pending(tg_id)
    await callback.message.edit_text(callback.message.text + "\n\nOtkloneno")
    await callback.answer("Zayavka otklonena")
    try:
        await bot.send_message(tg_id, t("rejected_notify", lang))
    except Exception:
        pass

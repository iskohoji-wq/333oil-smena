"""
Регистрация операторов:
- Незнакомый пользователь пишет боту → просим поделиться контактом и именем
  → заявка уходит владельцу на одобрение.
- Пока не одобрен — бот ничего больше не отвечает и не пускает дальше.
- Владелец одобряет/отклоняет через инлайн-кнопки.
"""
from aiogram import Router, F, Bot
from aiogram.filters import CommandStart
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


def contact_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t("share_contact_btn", lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def approval_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{tg_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{tg_id}"),
    ]])


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    tg_id = message.from_user.id

    # Владелец — сразу в свою панель, минуя регистрацию
    if tg_id in OWNER_IDS:
        from handlers.owner import send_owner_menu
        await send_owner_menu(message)
        return

    if storage.is_operator(tg_id):
        from handlers.shift import send_operator_menu
        await send_operator_menu(message)
        return

    if storage.is_pending(tg_id):
        await message.answer(t("already_pending", "ru"))
        return

    # Новый незнакомый пользователь — просим контакт
    await state.set_state(Registration.waiting_contact)
    await message.answer(t("welcome_unknown", "ru"), reply_markup=contact_keyboard("ru"))


@router.message(Registration.waiting_contact, F.contact)
async def got_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await state.set_state(Registration.waiting_name)
    await message.answer(t("ask_name", "ru"), reply_markup=ReplyKeyboardRemove())


@router.message(Registration.waiting_name, F.text)
async def got_name(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    phone = data.get("phone", "—")
    name = message.text.strip()
    tg_id = message.from_user.id

    storage.add_pending(tg_id, name, phone)
    await state.clear()
    await message.answer(t("request_sent", "ru"))

    # уведомляем всех владельцев
    for owner_id in OWNER_IDS:
        try:
            await bot.send_message(
                owner_id,
                "🆕 Новая заявка на регистрацию оператора:\n\n" + t("pending_item", "ru", name=name, phone=phone, tg_id=tg_id),
                reply_markup=approval_keyboard(tg_id),
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("approve:"))
async def cb_approve(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("Недоступно", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[1])
    pending = storage.get_pending().get(str(tg_id))
    if not pending:
        await callback.answer("Заявка уже обработана")
        return

    storage.add_operator(tg_id, pending["name"], pending["phone"])
    storage.remove_pending(tg_id)

    await callback.message.edit_text(callback.message.text + "\n\n✅ Одобрено")
    await callback.answer("Оператор добавлен")
    try:
        await bot.send_message(tg_id, t("approved_notify", storage.get_operator_lang(tg_id)))
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject:"))
async def cb_reject(callback: CallbackQuery, bot: Bot):
    if callback.from_user.id not in OWNER_IDS:
        await callback.answer("Недоступно", show_alert=True)
        return
    tg_id = int(callback.data.split(":")[1])
    pending = storage.get_pending().get(str(tg_id))
    if not pending:
        await callback.answer("Заявка уже обработана")
        return

    storage.remove_pending(tg_id)
    await callback.message.edit_text(callback.message.text + "\n\n❌ Отклонено")
    await callback.answer("Заявка отклонена")
    try:
        await bot.send_message(tg_id, t("rejected_notify", "ru"))
    except Exception:
        pass

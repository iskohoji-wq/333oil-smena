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


def owner_keyboard() -> ReplyKeyboardMarkup:
    buttons = []
    if OWNER_WEBAPP_URL:
        buttons.append([KeyboardButton(
            

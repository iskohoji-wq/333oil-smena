TEXTS = {
    "ru": {
        "welcome_unknown": (
            "Здравствуйте! Чтобы пользоваться ботом 333 OIL, нужно, чтобы владелец "
            "добавил вас как оператора.\n\nПоделитесь, пожалуйста, вашим именем и номером "
            "телефона — заявка уйдёт владельцу на одобрение."
        ),
        "share_contact_btn": "📱 Отправить номер телефона",
        "ask_name": "Как вас зовут (имя и фамилия)?",
        "request_sent": (
            "Спасибо! Заявка отправлена владельцу. Как только он подтвердит, "
            "бот сообщит вам, и можно будет начинать работу."
        ),
        "already_pending": "Ваша заявка уже отправлена владельцу и ожидает подтверждения.",
        "approved_notify": "✅ Владелец одобрил вашу заявку. Теперь вы можете сдавать смены в 333 OIL.",
        "rejected_notify": "К сожалению, владелец отклонил вашу заявку.",
        "choose_lang": "Выберите язык / Tilni tanlang:",
        "lang_set": "Язык установлен: Русский",
        "operator_menu": "Главное меню",
        "start_shift_btn": "🕐 Сдать смену",
        "owner_menu": "Панель владельца",
        "pending_list_empty": "Новых заявок нет.",
        "pending_item": "👤 {name}\n📞 {phone}\nID: {tg_id}",
        "approve_btn": "✅ Одобрить",
        "reject_btn": "❌ Отклонить",
        "shift_report_header": "📋 Отчёт смены — {date}\nОператор: {operator}",
    },
    "uz": {
        "welcome_unknown": (
            "Assalomu alaykum! 333 OIL botidan foydalanish uchun egasi sizni "
            "operator sifatida qo'shishi kerak.\n\nIltimos, ismingiz va telefon "
            "raqamingizni yuboring — so'rov egasiga tasdiqlash uchun yuboriladi."
        ),
        "share_contact_btn": "📱 Telefon raqamni yuborish",
        "ask_name": "Ismingiz va familiyangiz?",
        "request_sent": (
            "Rahmat! So'rov egasiga yuborildi. U tasdiqlashi bilan bot sizga "
            "xabar beradi va ishni boshlashingiz mumkin bo'ladi."
        ),
        "already_pending": "So'rovingiz allaqachon yuborilgan va tasdiqlanishini kutmoqda.",
        "approved_notify": "✅ Egasi so'rovingizni tasdiqladi. Endi 333 OIL'da smena topshirishingiz mumkin.",
        "rejected_notify": "Afsuski, egasi so'rovingizni rad etdi.",
        "choose_lang": "Tilni tanlang / Выберите язык:",
        "lang_set": "Til tanlandi: O'zbek",
        "operator_menu": "Asosiy menyu",
        "start_shift_btn": "🕐 Smenani topshirish",
        "owner_menu": "Egasi paneli",
        "pending_list_empty": "Yangi so'rovlar yo'q.",
        "pending_item": "👤 {name}\n📞 {phone}\nID: {tg_id}",
        "approve_btn": "✅ Tasdiqlash",
        "reject_btn": "❌ Rad etish",
        "shift_report_header": "📋 Smena hisoboti — {date}\nOperator: {operator}",
    },
}


def t(key: str, lang: str = "ru", **kwargs) -> str:
    lang = lang if lang in TEXTS else "ru"
    template = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    return template.format(**kwargs) if kwargs else template

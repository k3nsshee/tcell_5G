"""
Tcell 5G Campaign Bot v3
- Двуязычный (рус/тадж)
- Меню кнопок для пользователей и админа
- Исправлена пересылка фото через /pending
- Данные хранятся надёжно
"""

import logging
import json
import os
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler
)

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS_RAW = os.environ.get("ADMIN_IDS", "123456789")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_RAW.split(",")]
COVERAGE_MAP_FILE = "coverage_map.jpg"
DB_FILE = "participants.json"

# Дата розыгрыша — поменяй когда узнаешь
RAFFLE_DATE = os.environ.get("RAFFLE_DATE", "01.08.2025")

# ─────────────────────────────────────────────
# СОСТОЯНИЯ
# ─────────────────────────────────────────────
CHOOSE_LANG, WAIT_SCREENSHOT = range(2)

# ─────────────────────────────────────────────
# ТЕКСТЫ
# ─────────────────────────────────────────────
TEXTS = {
    "ru": {
        "welcome": (
            "👋 Добро пожаловать в акцию Tcell «Подключи 5G»!\n\n"
            "Вы уже подключили 5G сеть на своём телефоне?\n"
            "Отлично! Осталось совсем немного 🚀\n\n"
            "Сейчас я отправлю вам карту покрытия 5G сети Tcell."
        ),
        "map_caption": (
            "🗺 *Карта покрытия 5G сети Tcell*\n\n"
            "Убедитесь, что вы находитесь в зоне покрытия 5G.\n\n"
            "📱 *Что нужно сделать:*\n"
            "1. Зайдите в Настройки телефона\n"
            "2. Выберите «Мобильная сеть» → «Тип сети»\n"
            "3. Выберите *5G / LTE / 3G / 2G*\n"
            "4. Убедитесь, что в статус-баре отображается значок *5G*\n"
            "5. Сделайте скриншот с видимым значком 5G\n\n"
            "📤 Отправьте скриншот прямо сюда!"
        ),
        "got_screenshot": (
            "✅ Скриншот получен! Передаю на проверку.\n\n"
            "Как только скриншот будет проверен, вы получите ваш уникальный номер участника. "
            "Обычно это занимает несколько минут."
        ),
        "approved": (
            "🎉 *Поздравляем! Вы участник акции Tcell «Подключи 5G»!*\n\n"
            "🔢 Ваш уникальный номер участника:\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "          *#{number}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Сохраните этот номер — он понадобится при розыгрыше!\n"
            "Следите за результатами в нашем канале. Удачи! 🍀"
        ),
        "rejected": (
            "❌ К сожалению, ваш скриншот не прошёл проверку.\n\n"
            "Возможные причины:\n"
            "• На скриншоте не виден значок 5G\n"
            "• Скриншот нечёткий или повреждён\n\n"
            "Пожалуйста, отправьте новый скриншот 👇"
        ),
        "already_registered": (
            "ℹ️ Вы уже зарегистрированы в акции!\n\n"
            "Ваш номер участника: *#{number}*\n\n"
            "Следите за розыгрышем в нашем канале 🎁"
        ),
        "pending_wait": (
            "⏳ Ваш скриншот уже на проверке у администратора.\n"
            "Пожалуйста, подождите немного."
        ),
        "error_photo": "❗ Пожалуйста, отправьте именно фото (скриншот), а не файл или текст.",
        "raffle_info": "🎰 *Информация о розыгрыше*\n\n📅 Дата розыгрыша: *{date}*\n\n🎁 Призы будут объявлены на нашем канале.\nСледите за обновлениями!",
        "my_number": "🔢 Ваш номер участника: *#{number}*\n\nУдачи в розыгрыше! 🍀",
        "no_number": "❌ Вы ещё не зарегистрированы.\nНажмите /start чтобы участвовать.",
        "menu_btn_raffle": "🎰 Когда розыгрыш?",
        "menu_btn_number": "🔢 Мой номер",
        "menu_btn_status": "📋 Мой статус",
        "status_approved": "✅ Вы зарегистрированы! Номер: *#{number}*",
        "status_pending": "⏳ Ваш скриншот на проверке. Ожидайте.",
        "status_none": "❌ Вы ещё не участвуете. Нажмите /start",
    },
    "tj": {
        "welcome": (
            "👋 Хуш омадед ба акцияи Tcell «5G пайваст кун»!\n\n"
            "Шумо аллакай шабакаи 5G-ро дар телефонатон пайваст кардед?\n"
            "Аъло! Каме монд 🚀\n\n"
            "Ҳозун ман ба шумо харитаи фарогирии шабакаи 5G мефиристам."
        ),
        "map_caption": (
            "🗺 *Харитаи фарогирии шабакаи 5G Tcell*\n\n"
            "Боварӣ ҳосил кунед, ки шумо дар минтақаи фарогирии 5G ҳастед.\n\n"
            "📱 *Чӣ бояд кард:*\n"
            "1. Ба Танзимоти телефон равед\n"
            "2. «Шабакаи мобилӣ» → «Навъи шабака»-ро интихоб кунед\n"
            "3. *5G / LTE / 3G / 2G*-ро интихоб кунед\n"
            "4. Боварӣ ҳосил кунед, ки аломати *5G* намоён аст\n"
            "5. Аз экрани телефонатон скриншот гиред\n\n"
            "📤 Скриншотро ҳамин ҷо фиристед!"
        ),
        "got_screenshot": (
            "✅ Скриншот гирифта шуд! Барои тафтиш мефиристам.\n\n"
            "Баъди тафтиш рақами беназири иштирокчии шумо дода мешавад. "
            "Одатан ин чанд дақиқа вақт мегирад."
        ),
        "approved": (
            "🎉 *Табрик! Шумо иштирокчии акцияи Tcell «5G пайваст кун» ҳастед!*\n\n"
            "🔢 Рақами беназири иштирокчии шумо:\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "          *#{number}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Ин рақамро нигоҳ доред — ҳангоми қуръакашӣ лозим мешавад!\n"
            "Натиҷаҳоро дар канали мо пайгирӣ кунед. Бахт! 🍀"
        ),
        "rejected": (
            "❌ Мутаассифона, скриншоти шумо тафтишро нагузашт.\n\n"
            "Сабабҳои эҳтимолӣ:\n"
            "• Дар скриншот аломати 5G намоён нест\n"
            "• Скриншот норавшан ё вайрон аст\n\n"
            "Лутфан скриншоти наверо фиристед 👇"
        ),
        "already_registered": (
            "ℹ️ Шумо аллакай дар акция бақайд гирифта шудед!\n\n"
            "Рақами иштирокчии шумо: *#{number}*\n\n"
            "Қуръакаширо дар канали мо пайгирӣ кунед 🎁"
        ),
        "pending_wait": (
            "⏳ Скриншоти шумо аллакай назди маъмур барои тафтиш аст.\n"
            "Лутфан каме интизор шавед."
        ),
        "error_photo": "❗ Лутфан акс (скриншот) фиристед, на файл ё матн.",
        "raffle_info": "🎰 *Маълумот дар бораи қуръакашӣ*\n\n📅 Санаи қуръакашӣ: *{date}*\n\n🎁 Ҷоизаҳо дар канали мо эълон мешаванд.\nПайгирӣ кунед!",
        "my_number": "🔢 Рақами иштирокчии шумо: *#{number}*\n\nДар қуръакашӣ бахт! 🍀",
        "no_number": "❌ Шумо ҳанӯз бақайд гирифта нашудед.\n/start -ро пахш кунед.",
        "menu_btn_raffle": "🎰 Қуръакашӣ кай?",
        "menu_btn_number": "🔢 Рақами ман",
        "menu_btn_status": "📋 Ҳолати ман",
        "status_approved": "✅ Шумо бақайд гирифтед! Рақам: *#{number}*",
        "status_pending": "⏳ Скриншоти шумо тафтиш мешавад. Интизор шавед.",
        "status_none": "❌ Шумо иштирок намекунед. /start -ро пахш кунед",
    }
}

# ─────────────────────────────────────────────
# БД
# ─────────────────────────────────────────────

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"participants": {}, "counter": 0, "pending": {}}


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_next_number(db: dict) -> str:
    db["counter"] += 1
    return str(db["counter"]).zfill(3)


# ─────────────────────────────────────────────
# ХЕЛПЕРЫ
# ─────────────────────────────────────────────

def lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
    ]])


def user_menu(lang: str):
    """Меню кнопок для обычных пользователей"""
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]["menu_btn_raffle"])],
        [KeyboardButton(TEXTS[lang]["menu_btn_number"]), KeyboardButton(TEXTS[lang]["menu_btn_status"])],
    ], resize_keyboard=True)


def admin_menu():
    """Меню кнопок для администратора"""
    return ReplyKeyboardMarkup([
        ["📊 Статистика", "⏳ На проверке"],
        ["📤 Рассылка", "📅 Изменить дату"],
    ], resize_keyboard=True)


def txt(lang: str, key: str, **kwargs) -> str:
    text = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def get_lang(context) -> str:
    return context.user_data.get("lang", "ru")


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ — ПОЛЬЗОВАТЕЛЬ
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = str(update.effective_user.id)

    # Если это админ — показываем админ-меню
    if update.effective_user.id in ADMIN_IDS:
        await update.message.reply_text(
            "👨‍💼 *Панель администратора Tcell 5G*\n\nВыберите действие:",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🌐 Выберите язык / Забонро интихоб кунед:",
        reply_markup=lang_keyboard()
    )
    return CHOOSE_LANG


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang
    user_id = str(query.from_user.id)
    db = load_db()

    # Уже подтверждён
    if user_id in db["participants"] and db["participants"][user_id].get("approved"):
        number = db["participants"][user_id]["number"]
        await query.edit_message_text(
            txt(lang, "already_registered", number=number),
            parse_mode="Markdown"
        )
        await query.message.reply_text("Выберите действие:", reply_markup=user_menu(lang))
        return ConversationHandler.END

    # Ждёт проверки
    if user_id in db["pending"]:
        await query.edit_message_text(txt(lang, "pending_wait"))
        return ConversationHandler.END

    # Новый пользователь
    await query.edit_message_text(txt(lang, "welcome"))

    try:
        with open(COVERAGE_MAP_FILE, "rb") as photo:
            await query.message.reply_photo(
                photo=photo,
                caption=txt(lang, "map_caption"),
                parse_mode="Markdown"
            )
    except FileNotFoundError:
        await query.message.reply_text(txt(lang, "map_caption"), parse_mode="Markdown")

    return WAIT_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.message.photo:
        lang = get_lang(context)
        await update.message.reply_text(txt(lang, "error_photo"))
        return WAIT_SCREENSHOT

    user = update.message.from_user
    user_id = str(user.id)
    lang = context.user_data.get("lang", "ru")
    db = load_db()

    if user_id in db["participants"] and db["participants"][user_id].get("approved"):
        number = db["participants"][user_id]["number"]
        await update.message.reply_text(
            txt(lang, "already_registered", number=number),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if user_id in db["pending"]:
        await update.message.reply_text(txt(lang, "pending_wait"))
        return WAIT_SCREENSHOT

    # Скачиваем фото и сохраняем как байты в базу
    photo_file = await update.message.photo[-1].get_file()
    photo_bytes = await photo_file.download_as_bytearray()
    photo_b64 = __import__("base64").b64encode(photo_bytes).decode()

    db["pending"][user_id] = {
        "user_id": user_id,
        "username": user.username or "",
        "full_name": user.full_name,
        "lang": lang,
        "file_id": update.message.photo[-1].file_id,
        "photo_b64": photo_b64,
        "timestamp": datetime.now().isoformat(),
    }
    save_db(db)

    await update.message.reply_text(
        txt(lang, "got_screenshot"),
        reply_markup=user_menu(lang)
    )

    # Отправляем админам — используем скачанные байты
    kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}"),
    ]])
    caption = (
        f"📸 *Новый скриншот на проверку*\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 @{user.username or 'нет'}\n"
        f"🌐 Язык: {'Русский' if lang == 'ru' else 'Тоҷикӣ'}\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=__import__("io").BytesIO(photo_bytes),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=kbd
            )
        except Exception as e:
            logging.error(f"Ошибка отправки фото админу {admin_id}: {e}")

    return WAIT_SCREENSHOT


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ — МЕНЮ ПОЛЬЗОВАТЕЛЯ (кнопки)
# ─────────────────────────────────────────────

async def handle_user_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = str(update.effective_user.id)
    lang = get_lang(context)
    db = load_db()

    raffle_btns = [TEXTS["ru"]["menu_btn_raffle"], TEXTS["tj"]["menu_btn_raffle"]]
    number_btns = [TEXTS["ru"]["menu_btn_number"], TEXTS["tj"]["menu_btn_number"]]
    status_btns = [TEXTS["ru"]["menu_btn_status"], TEXTS["tj"]["menu_btn_status"]]

    if text in raffle_btns:
        await update.message.reply_text(
            txt(lang, "raffle_info", date=RAFFLE_DATE),
            parse_mode="Markdown"
        )

    elif text in number_btns:
        if user_id in db["participants"] and db["participants"][user_id].get("approved"):
            number = db["participants"][user_id]["number"]
            await update.message.reply_text(txt(lang, "my_number", number=number), parse_mode="Markdown")
        else:
            await update.message.reply_text(txt(lang, "no_number"))

    elif text in status_btns:
        if user_id in db["participants"] and db["participants"][user_id].get("approved"):
            number = db["participants"][user_id]["number"]
            await update.message.reply_text(txt(lang, "status_approved", number=number), parse_mode="Markdown")
        elif user_id in db["pending"]:
            await update.message.reply_text(txt(lang, "status_pending"))
        else:
            await update.message.reply_text(txt(lang, "status_none"))


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ — МЕНЮ АДМИНА (кнопки)
# ─────────────────────────────────────────────

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return

    db = load_db()

    if text == "📊 Статистика":
        total = len(db["participants"])
        pending = len(db["pending"])
        await update.message.reply_text(
            f"📊 *Статистика акции Tcell 5G*\n\n"
            f"✅ Подтверждённых участников: *{total}*\n"
            f"⏳ Ожидают проверки: *{pending}*\n"
            f"🔢 Следующий номер: *{str(db['counter'] + 1).zfill(3)}*\n"
            f"📅 Дата розыгрыша: *{RAFFLE_DATE}*",
            parse_mode="Markdown"
        )

    elif text == "⏳ На проверке":
        if not db["pending"]:
            await update.message.reply_text("✅ Нет скриншотов на проверке.")
            return
        await update.message.reply_text(f"⏳ Скриншотов на проверке: {len(db['pending'])}. Пересылаю...")
        import base64, io
        for uid, info in db["pending"].items():
            kbd = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{uid}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{uid}"),
            ]])
            caption = (
                f"📸 *Скриншот на проверку*\n\n"
                f"👤 {info['full_name']}\n"
                f"🆔 ID: `{uid}`\n"
                f"📛 @{info.get('username') or 'нет'}\n"
                f"🌐 Язык: {'Русский' if info.get('lang') == 'ru' else 'Тоҷикӣ'}\n"
                f"🕐 {info.get('timestamp', '')[:16].replace('T', ' ')}"
            )
            try:
                photo_bytes = base64.b64decode(info["photo_b64"])
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=io.BytesIO(photo_bytes),
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=kbd
                )
            except Exception as e:
                await update.message.reply_text(
                    f"⚠️ Не удалось показать фото для {info['full_name']}\n\n{caption}",
                    parse_mode="Markdown",
                    reply_markup=kbd
                )

    elif text == "📤 Рассылка":
        context.user_data["waiting_broadcast"] = True
        await update.message.reply_text(
            "✏️ Напишите текст для рассылки всем участникам.\n\n"
            "Для отмены напишите /cancel"
        )

    elif text == "📅 Изменить дату":
        context.user_data["waiting_date"] = True
        await update.message.reply_text(
            f"📅 Текущая дата розыгрыша: *{RAFFLE_DATE}*\n\n"
            "Напишите новую дату в формате ДД.ММ.ГГГГ\n"
            "Например: 15.07.2025\n\n"
            "Для отмены напишите /cancel",
            parse_mode="Markdown"
        )


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текстового ввода от админа (рассылка, дата)"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    if context.user_data.get("waiting_broadcast"):
        context.user_data.pop("waiting_broadcast")
        message_text = update.message.text
        db = load_db()
        success, failed = 0, 0
        for uid in db["participants"]:
            try:
                await context.bot.send_message(chat_id=int(uid), text=message_text)
                success += 1
            except Exception:
                failed += 1
        await update.message.reply_text(
            f"📤 Рассылка завершена.\n✅ Отправлено: {success}\n❌ Ошибок: {failed}",
            reply_markup=admin_menu()
        )

    elif context.user_data.get("waiting_date"):
        context.user_data.pop("waiting_date")
        global RAFFLE_DATE
        RAFFLE_DATE = update.message.text.strip()
        await update.message.reply_text(
            f"✅ Дата розыгрыша обновлена: *{RAFFLE_DATE}*",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )


# ─────────────────────────────────────────────
# ХЕНДЛЕР — РЕШЕНИЕ АДМИНА (одобрить/отклонить)
# ─────────────────────────────────────────────

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id

    if admin_id not in ADMIN_IDS:
        await query.answer("⛔ У вас нет прав.", show_alert=True)
        return

    await query.answer()
    action, target_user_id = query.data.split("_", 1)
    db = load_db()

    if target_user_id not in db["pending"]:
        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано.",
            parse_mode="Markdown"
        )
        return

    pending_info = db["pending"].pop(target_user_id)
    lang = pending_info.get("lang", "ru")

    if action == "approve":
        number = get_next_number(db)
        db["participants"][target_user_id] = {
            **{k: v for k, v in pending_info.items() if k != "photo_b64"},
            "number": number,
            "approved": True,
            "approved_at": datetime.now().isoformat(),
        }
        save_db(db)

        msg = TEXTS[lang]["approved"].replace("{number}", number)
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=msg,
                parse_mode="Markdown",
                reply_markup=user_menu(lang)
            )
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя: {e}")

        await query.edit_message_caption(
            caption=(query.message.caption or "") + f"\n\n✅ *Одобрено.* Номер: *#{number}*",
            parse_mode="Markdown"
        )

    elif action == "reject":
        save_db(db)
        msg = TEXTS[lang]["rejected"]
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя: {e}")

        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n❌ *Отклонено.*",
            parse_mode="Markdown"
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("waiting_broadcast", None)
    context.user_data.pop("waiting_date", None)
    await update.message.reply_text(
        "Отменено. Нажмите /start чтобы начать заново.",
        reply_markup=admin_menu() if update.effective_user.id in ADMIN_IDS else ReplyKeyboardMarkup([[]], resize_keyboard=True)
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────

def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_LANG: [CallbackQueryHandler(choose_language, pattern="^lang_")],
            WAIT_SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_screenshot),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )

    # Определяем кнопки меню пользователя для фильтрации
    all_user_btns = (
        [v["menu_btn_raffle"] for v in TEXTS.values()] +
        [v["menu_btn_number"] for v in TEXTS.values()] +
        [v["menu_btn_status"] for v in TEXTS.values()]
    )
    admin_btns = ["📊 Статистика", "⏳ На проверке", "📤 Рассылка", "📅 Изменить дату"]

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve|reject)_"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(all_user_btns)), handle_user_menu))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(admin_btns)), handle_admin_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))

    print("🤖 Бот Tcell 5G v3 запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

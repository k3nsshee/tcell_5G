"""
Tcell 5G Campaign Bot
- Двуязычный (рус/тадж)
- asyncio.Lock для безопасной параллельной работы
- PicklePersistence — запоминает состояние после перезапуска
- Тройной fallback для пересылки фото
- Дата розыгрыша хранится в БД
- python-dotenv для локальной разработки
- Причины отклонения на выбор администратора
- Позиция в очереди для пользователя
- Дубликат-детектор по хешу фото
- Экспорт участников в CSV
"""

import asyncio
import base64
import csv
import hashlib
import io
import logging
import json
import os
import random
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, PicklePersistence
)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─────────────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────────────
BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_IDS = [int(x.strip()) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()]
COVERAGE_MAP_FILE = "coverage_map.jpg"
DB_FILE = "participants.json"
PERSISTENCE_FILE = "bot_persistence.pkl"
DEFAULT_RAFFLE_DATE = os.environ.get("RAFFLE_DATE", "01.08.2025")

db_lock = asyncio.Lock()

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
            "📍 Вы в очереди: *#{position}*\n\n"
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
            "Удачи! 🍀"
        ),
        "rejected_no5g": (
            "❌ Скриншот не прошёл проверку.\n\n"
            "Причина: на скриншоте не виден значок *5G* в статус-баре.\n\n"
            "Убедитесь, что значок 5G отображается, и отправьте новый скриншот 👇"
        ),
        "rejected_blurry": (
            "❌ Скриншот не прошёл проверку.\n\n"
            "Причина: скриншот нечёткий или плохо читается.\n\n"
            "Пожалуйста, сделайте чёткий скриншот и отправьте снова 👇"
        ),
        "rejected_other": (
            "❌ Скриншот не прошёл проверку.\n\n"
            "Убедитесь, что значок *5G* чётко виден в статус-баре, и отправьте новый скриншот 👇"
        ),
        "already_registered": (
            "ℹ️ Вы уже зарегистрированы в акции!\n\n"
            "Ваш номер участника: *#{number}*\n\n"
            "Следите за розыгрышем 🎁"
        ),
        "pending_wait": (
            "⏳ Ваш скриншот уже на проверке у администратора.\n"
            "Пожалуйста, подождите немного."
        ),
        "error_photo": "❗ Пожалуйста, отправьте именно фото (скриншот), а не файл или текст.",
        "raffle_info": "🎰 *Информация о розыгрыше*\n\n📅 Дата розыгрыша: *{date}*\n\n🎁 Призы будут объявлены в боте.",
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
            "📍 Шумо дар навбат: *#{position}*\n\n"
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
            "Бахт! 🍀"
        ),
        "rejected_no5g": (
            "❌ Скриншоти шумо тафтишро нагузашт.\n\n"
            "Сабаб: дар скриншот аломати *5G* дар статус-бар намоён нест.\n\n"
            "Боварӣ ҳосил кунед, ки аломати 5G намоён аст ва скриншоти наверо фиристед 👇"
        ),
        "rejected_blurry": (
            "❌ Скриншоти шумо тафтишро нагузашт.\n\n"
            "Сабаб: скриншот норавшан ё хонда намешавад.\n\n"
            "Лутфан скриншоти равшан гиред ва дубора фиристед 👇"
        ),
        "rejected_other": (
            "❌ Скриншоти шумо тафтишро нагузашт.\n\n"
            "Боварӣ ҳосил кунед, ки аломати *5G* дар статус-бар намоён аст ва скриншоти наверо фиристед 👇"
        ),
        "already_registered": (
            "ℹ️ Шумо аллакай дар акция бақайд гирифта шудед!\n\n"
            "Рақами иштирокчии шумо: *#{number}*\n\n"
            "Қуръакаширо пайгирӣ кунед 🎁"
        ),
        "pending_wait": (
            "⏳ Скриншоти шумо аллакай назди маъмур барои тафтиш аст.\n"
            "Лутфан каме интизор шавед."
        ),
        "error_photo": "❗ Лутфан акс (скриншот) фиристед, на файл ё матн.",
        "raffle_info": "🎰 *Маълумот дар бораи қуръакашӣ*\n\n📅 Санаи қуръакашӣ: *{date}*\n\n🎁 Ҷоизаҳо дар бот эълон мешаванд.",
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

# Причины отклонения — метки кнопок для админа
REJECT_REASONS = {
    "no5g":  "❌ Нет значка 5G",
    "blurry": "📷 Нечёткий",
    "other":  "🚫 Иное",
}

# ─────────────────────────────────────────────
# БД
# ─────────────────────────────────────────────

def load_db() -> dict:
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)
        db.setdefault("raffle_date", DEFAULT_RAFFLE_DATE)
        db.setdefault("photo_hashes", {})
        return db
    return {
        "participants": {},
        "counter": 0,
        "pending": {},
        "raffle_date": DEFAULT_RAFFLE_DATE,
        "photo_hashes": {},  # hash -> user_id, для детекции дубликатов
    }


def save_db(db: dict):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def get_next_number(db: dict) -> str:
    db["counter"] += 1
    return str(db["counter"]).zfill(3)


def photo_hash(photo_bytes: bytes) -> str:
    return hashlib.md5(photo_bytes).hexdigest()


# ─────────────────────────────────────────────
# ХЕЛПЕРЫ
# ─────────────────────────────────────────────

def lang_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
    ]])


def user_menu(lang: str):
    return ReplyKeyboardMarkup([
        [KeyboardButton(TEXTS[lang]["menu_btn_raffle"])],
        [KeyboardButton(TEXTS[lang]["menu_btn_number"]), KeyboardButton(TEXTS[lang]["menu_btn_status"])],
    ], resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup([
        ["📊 Статистика", "⏳ На проверке"],
        ["📤 Рассылка", "📅 Изменить дату"],
        ["📥 Экспорт CSV"],
    ], resize_keyboard=True)


def txt(lang: str, key: str, **kwargs) -> str:
    text = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


def get_lang(context) -> str:
    return context.user_data.get("lang", "ru")


def reject_reason_keyboard(user_id: str):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(label, callback_data=f"rejectconfirm_{user_id}_{code}")
        for code, label in REJECT_REASONS.items()
    ]])


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ — ПОЛЬЗОВАТЕЛЬ
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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

    async with db_lock:
        db = load_db()

        if user_id in db["participants"] and db["participants"][user_id].get("approved"):
            number = db["participants"][user_id]["number"]
            await query.edit_message_text(
                txt(lang, "already_registered", number=number),
                parse_mode="Markdown"
            )
            await query.message.reply_text("Выберите действие:", reply_markup=user_menu(lang))
            return ConversationHandler.END

        if user_id in db["pending"]:
            await query.edit_message_text(txt(lang, "pending_wait"))
            return ConversationHandler.END

    await query.edit_message_text(txt(lang, "welcome"))

    await asyncio.sleep(5)

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

    async with db_lock:
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

        # Скачиваем фото
        photo_file = await update.message.photo[-1].get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_bytes = bytes(photo_bytes)
        p_hash = photo_hash(photo_bytes)
        photo_b64 = base64.b64encode(photo_bytes).decode()

        # Проверка дубликата
        duplicate_of = db["photo_hashes"].get(p_hash)

        queue_position = random.randint(10000, 99999)

        db["pending"][user_id] = {
            "user_id": user_id,
            "username": user.username or "",
            "full_name": user.full_name,
            "lang": lang,
            "file_id": update.message.photo[-1].file_id,
            "photo_b64": photo_b64,
            "photo_hash": p_hash,
            "timestamp": datetime.now().isoformat(),
        }
        save_db(db)

    await update.message.reply_text(
        txt(lang, "got_screenshot", position=queue_position),
        parse_mode="Markdown",
        reply_markup=user_menu(lang)
    )

    # Отправляем админам
    approve_reject_kbd = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}"),
    ]])

    dup_warning = f"\n⚠️ *ДУБЛИКАТ* — это фото уже отправлял `{duplicate_of}`" if duplicate_of else ""
    caption = (
        f"📸 *Новый скриншот на проверку*\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 @{user.username or 'нет'}\n"
        f"🌐 Язык: {'Русский' if lang == 'ru' else 'Тоҷикӣ'}\n"
        f"🕐 {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        f"{dup_warning}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=io.BytesIO(photo_bytes),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=approve_reject_kbd
            )
        except Exception as e:
            logging.error(f"Ошибка отправки фото админу {admin_id}: {e}")

    return WAIT_SCREENSHOT


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ — МЕНЮ ПОЛЬЗОВАТЕЛЯ
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
            txt(lang, "raffle_info", date=db.get("raffle_date", DEFAULT_RAFFLE_DATE)),
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
# ХЕНДЛЕРЫ — МЕНЮ АДМИНА
# ─────────────────────────────────────────────

async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.effective_user.id

    if user_id not in ADMIN_IDS:
        return

    async with db_lock:
        db = load_db()

    if text == "📊 Статистика":
        total = len(db["participants"])
        pending = len(db["pending"])
        await update.message.reply_text(
            f"📊 *Статистика акции Tcell 5G*\n\n"
            f"✅ Подтверждённых участников: *{total}*\n"
            f"⏳ Ожидают проверки: *{pending}*\n"
            f"🔢 Следующий номер: *{str(db['counter'] + 1).zfill(3)}*\n"
            f"📅 Дата розыгрыша: *{db.get('raffle_date', DEFAULT_RAFFLE_DATE)}*",
            parse_mode="Markdown"
        )

    elif text == "⏳ На проверке":
        if not db["pending"]:
            await update.message.reply_text("✅ Нет скриншотов на проверке.")
            return

        await update.message.reply_text(f"⏳ Скриншотов на проверке: {len(db['pending'])}. Пересылаю...")

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
            sent = False

            if info.get("photo_b64"):
                try:
                    photo_bytes = base64.b64decode(info["photo_b64"])
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=io.BytesIO(photo_bytes),
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=kbd
                    )
                    sent = True
                except Exception as e:
                    logging.warning(f"photo_b64 не сработал для {uid}: {e}")

            if not sent and info.get("file_id"):
                try:
                    await context.bot.send_photo(
                        chat_id=user_id,
                        photo=info["file_id"],
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=kbd
                    )
                    sent = True
                except Exception as e:
                    logging.warning(f"file_id не сработал для {uid}: {e}")

            if not sent:
                await update.message.reply_text(
                    f"📸 Фото недоступно (старая запись)\n\n{caption}",
                    parse_mode="Markdown",
                    reply_markup=kbd
                )

    elif text == "📤 Рассылка":
        context.user_data["waiting_broadcast"] = True
        await update.message.reply_text(
            "✏️ Напишите текст для рассылки всем участникам.\n\n"
            "Поддерживается *жирный*, _курсив_, `код`.\n\n"
            "Для отмены напишите /cancel"
        )

    elif text == "📅 Изменить дату":
        context.user_data["waiting_date"] = True
        current = db.get("raffle_date", DEFAULT_RAFFLE_DATE)
        await update.message.reply_text(
            f"📅 Текущая дата розыгрыша: *{current}*\n\n"
            "Напишите новую дату в формате ДД.ММ.ГГГГ\n"
            "Например: 15.07.2025\n\n"
            "Для отмены напишите /cancel",
            parse_mode="Markdown"
        )

    elif text == "📥 Экспорт CSV":
        if not db["participants"]:
            await update.message.reply_text("📭 Нет подтверждённых участников для экспорта.")
            return

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Номер", "Telegram ID", "Имя", "Username", "Язык", "Дата подтверждения"])
        for uid, info in sorted(db["participants"].items(), key=lambda x: int(x[1].get("number", "0"))):
            writer.writerow([
                info.get("number", ""),
                uid,
                info.get("full_name", ""),
                f"@{info.get('username', '')}" if info.get("username") else "",
                "Русский" if info.get("lang") == "ru" else "Тоҷикӣ",
                info.get("approved_at", "")[:16].replace("T", " "),
            ])

        csv_bytes = output.getvalue().encode("utf-8-sig")  # utf-8-sig для корректного открытия в Excel
        filename = f"tcell_5g_participants_{datetime.now().strftime('%d%m%Y')}.csv"
        await context.bot.send_document(
            chat_id=user_id,
            document=io.BytesIO(csv_bytes),
            filename=filename,
            caption=f"📥 Экспорт участников — {len(db['participants'])} чел.\n{datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if context.user_data.get("waiting_broadcast"):
        context.user_data.pop("waiting_broadcast")
        message_text = update.message.text
        async with db_lock:
            db = load_db()
            participant_ids = list(db["participants"].keys())
        success, failed = 0, 0
        for uid in participant_ids:
            try:
                await context.bot.send_message(chat_id=int(uid), text=message_text, parse_mode="Markdown")
                success += 1
            except Exception:
                failed += 1
        await update.message.reply_text(
            f"📤 Рассылка завершена.\n✅ Отправлено: {success}\n❌ Ошибок: {failed}",
            reply_markup=admin_menu()
        )

    elif context.user_data.get("waiting_date"):
        context.user_data.pop("waiting_date")
        new_date = update.message.text.strip()
        async with db_lock:
            db = load_db()
            db["raffle_date"] = new_date
            save_db(db)
        await update.message.reply_text(
            f"✅ Дата розыгрыша обновлена: *{new_date}*",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )


# ─────────────────────────────────────────────
# ХЕНДЛЕР — РЕШЕНИЕ АДМИНА
# ─────────────────────────────────────────────

async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin_id = query.from_user.id

    if admin_id not in ADMIN_IDS:
        await query.answer("⛔ У вас нет прав.", show_alert=True)
        return

    await query.answer()
    data = query.data

    # ── Одобрение ──────────────────────────────
    if data.startswith("approve_"):
        target_user_id = data[len("approve_"):]

        async with db_lock:
            db = load_db()

            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано.",
                    parse_mode="Markdown"
                )
                return

            pending_info = db["pending"].pop(target_user_id)
            lang = pending_info.get("lang", "ru")
            number = get_next_number(db)
            p_hash = pending_info.get("photo_hash")

            db["participants"][target_user_id] = {
                **{k: v for k, v in pending_info.items() if k != "photo_b64"},
                "number": number,
                "approved": True,
                "approved_at": datetime.now().isoformat(),
            }
            # Сохраняем хеш фото → user_id для детекции дубликатов
            if p_hash:
                db["photo_hashes"][p_hash] = target_user_id

            total = len(db["participants"])
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
            caption=(query.message.caption or "") + f"\n\n✅ *Одобрено.* Номер: *#{number}* | Всего: {total}",
            parse_mode="Markdown"
        )

    # ── Отклонение — показать причины ──────────
    elif data.startswith("reject_") and not data.startswith("rejectconfirm_"):
        target_user_id = data[len("reject_"):]

        async with db_lock:
            db = load_db()
            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано.",
                    parse_mode="Markdown"
                )
                return

        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n❓ *Укажите причину отклонения:*",
            parse_mode="Markdown",
            reply_markup=reject_reason_keyboard(target_user_id)
        )

    # ── Отклонение — подтверждение с причиной ──
    elif data.startswith("rejectconfirm_"):
        parts = data.split("_", 2)  # ["rejectconfirm", uid, reason_code]
        if len(parts) != 3:
            return
        _, target_user_id, reason_code = parts

        async with db_lock:
            db = load_db()

            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано.",
                    parse_mode="Markdown"
                )
                return

            pending_info = db["pending"].pop(target_user_id)
            lang = pending_info.get("lang", "ru")
            save_db(db)

        reason_key = f"rejected_{reason_code}"
        msg = TEXTS[lang].get(reason_key, TEXTS[lang]["rejected_other"])

        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя: {e}")

        reason_label = REJECT_REASONS.get(reason_code, reason_code)
        await query.edit_message_caption(
            caption=(query.message.caption or "") + f"\n\n❌ *Отклонено.* Причина: {reason_label}",
            parse_mode="Markdown"
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("waiting_broadcast", None)
    context.user_data.pop("waiting_date", None)
    await update.message.reply_text(
        "Отменено.",
        reply_markup=admin_menu() if update.effective_user.id in ADMIN_IDS else ReplyKeyboardRemove()
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

    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).build()

    all_user_btns = (
        [v["menu_btn_raffle"] for v in TEXTS.values()] +
        [v["menu_btn_number"] for v in TEXTS.values()] +
        [v["menu_btn_status"] for v in TEXTS.values()]
    )
    admin_btns = ["📊 Статистика", "⏳ На проверке", "📤 Рассылка", "📅 Изменить дату", "📥 Экспорт CSV"]

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSE_LANG: [CallbackQueryHandler(choose_language, pattern="^lang_")],
            WAIT_SCREENSHOT: [
                MessageHandler(filters.PHOTO, receive_screenshot),
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_screenshot),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        name="registration_conversation",
        persistent=True,
        per_user=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve_|reject_|rejectconfirm_)"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(all_user_btns)), handle_user_menu))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(admin_btns)), handle_admin_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    # Fallback: фото от пользователей вне ConversationHandler (после отклонения)
    app.add_handler(MessageHandler(filters.PHOTO, receive_screenshot))

    print("🤖 Бот Tcell 5G запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

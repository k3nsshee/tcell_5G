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
import pg8000.native
import urllib.parse
import base64
import hashlib
import io
import logging
import json
import os
import random
import re
from datetime import datetime, time, timedelta, timezone

import openpyxl
from openpyxl.styles import Font
from telegram import (
    Update, BotCommand, BotCommandScopeChat,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters, ConversationHandler, PicklePersistence
)
from telegram.helpers import escape_markdown

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
DATABASE_URL = os.environ.get("DATABASE_URL", "")
COVERAGE_MAP_FILE = "coverage_map.jpg"
PERSISTENCE_FILE = "bot_persistence.pkl"
DEFAULT_RAFFLE_DATE = os.environ.get("RAFFLE_DATE", "01.08.2025")
PENDING_PAGE_SIZE = 10  # сколько скриншотов показывать админу за одну порцию

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
        "welcome": "👋 Добро пожаловать в розыгрыш «Подключи 5G»!",
        "map_caption": (
            "🗺 *Карта покрытия 5G сети Tcell*\n\n"
            "📱 *Что нужно сделать:*\n"
            "1. Убедитесь, что вы набрали USSD-команду `*871*5#`\n"
            "2. Зайдите в настройки телефона и поменяйте настройки сети на *5G*\n"
            "3. Сделайте скриншот, где возле антенны отображается *5G*\n\n"
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
            "Удачи! 🍀"
        ),
        "rejected_no5g": (
            "❌ Скриншот не прошёл проверку.\n\n"
            "Причина: на скриншоте не виден значок *5G* возле антенны.\n\n"
            "Убедитесь, что значок 5G отображается возле антенны, и отправьте новый скриншот 👇"
        ),
        "already_registered": (
            "ℹ️ Вы уже зарегистрированы в розыгрыше!\n\n"
            "Ваш номер участника: *#{number}*\n\n"
            "Следите за розыгрышем 🎁"
        ),
        "pending_wait": (
            "⏳ Ваш скриншот уже на проверке у администратора.\n"
            "Пожалуйста, подождите немного."
        ),
        "error_photo": "❗ Пожалуйста, отправьте именно фото (скриншот), а не файл или текст.",
        "raffle_info": "🎰 *Информация о розыгрыше*\n\n📅 Дата розыгрыша: *{date}*\n\n🎁 Победители будут объявлены в боте.",
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
        "welcome": "👋 Хуш омадед ба икдоми «Ба 5G пайваст шав»!",
        "map_caption": (
            "🗺 *Харитаи фарогирии шабакаи 5G Tcell*\n\n"
            "📱 *Чӣ бояд кард:*\n"
            "1. Бори дигар санҷед, ки шумо фармони `*871*5#` фаъол кардед\n"
            "2. Танзимоти телефони худро санҷед, ки шабакаи *5G* интихоб шудааст\n"
            "3. Скриншот кунед, ки дар он шабакаи *5G* дар назди антенна намоён бошад\n\n"
            "📤 Скриншотро ҳамин ҷо фиристед!"
        ),
        "got_screenshot": (
            "✅ Скриншот гирифта шуд! Барои тафтиш мефиристам.\n\n"
            "Баъди тафтиш рақами беназири иштирокчии шумо дода мешавад. "
            "Одатан ин чанд дақиқа вақт мегирад."
        ),
        "approved": (
            "🎉 *Табрик! Шумо иштирокчии икдоми «Ба 5G пайваст шав» ҳастед!*\n\n"
            "🔢 Рақами беназири иштирокчии шумо:\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "          *#{number}*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Ин рақамро нигоҳ доред — ҳангоми қуръакашӣ лозим мешавад!\n"
            "Бахт! 🍀"
        ),
        "rejected_no5g": (
            "❌ Скриншоти шумо тафтишро нагузашт.\n\n"
            "Сабаб: дар скриншот аломати *5G* дар назди антенна намоён нест.\n\n"
            "Аломати 5G-ро намоён кунед ва скриншоти наверо фиристед 👇"
        ),
        "already_registered": (
            "ℹ️ Шумо аллакай дар икдом бақайд гирифта шудед!\n\n"
            "Рақами иштирокчии шумо: *#{number}*\n\n"
            "Қуръакаширо пайгирӣ кунед 🎁"
        ),
        "pending_wait": (
            "⏳ Скриншоти шумо аллакай назди маъмур барои тафтиш аст.\n"
            "Лутфан каме интизор шавед."
        ),
        "error_photo": "❗ Лутфан акс (скриншот) фиристед, на файл ё матн.",
        "raffle_info": "🎰 *Маълумот дар бораи қуръакашӣ*\n\n📅 Санаи қуръакашӣ: *{date}*\n\n🎁 Голибон дар бот эълон мешаванд.",
        "my_number": "🔢 Рақами иштирокчии шумо: *#{number}*\n\nДар қуръакашӣ барор хохонем! 🍀",
        "no_number": "❌ Шумо холо бақайд гирифта нашудед.\n/start -ро пахш кунед.",
        "menu_btn_raffle": "🎰 Қуръакашӣ кай?",
        "menu_btn_number": "🔢 Рақами ман",
        "menu_btn_status": "📋 Ҳолати ман",
        "status_approved": "✅ Шумо бақайд гирифта шудед! Рақам: *#{number}*",
        "status_pending": "⏳ Скриншоти шумо тафтиш шуда истодааст. Интизор шавед.",
        "status_none": "❌ Шумо иштирок намекунед. /start -ро пахш кунед",
    }
}

# Причины отклонения — метки кнопок для админа
REJECT_REASONS = {
    "no5g": "❌ Нет значка 5G",
}

# ─────────────────────────────────────────────
# БД — PostgreSQL (psycopg2)
# ─────────────────────────────────────────────

_DEFAULT_DB = {
    "participants": {},
    "counter": 0,
    "pending": {},
    "raffle_date": DEFAULT_RAFFLE_DATE,
    "photo_hashes": {},
}


def get_conn():
    r = urllib.parse.urlparse(DATABASE_URL)
    return pg8000.native.Connection(
        host=r.hostname,
        port=r.port or 5432,
        database=r.path.lstrip("/"),
        user=r.username,
        password=r.password,
        ssl_context=False,
    )


def init_db_sync():
    conn = get_conn()
    conn.run("""
        CREATE TABLE IF NOT EXISTS bot_state (
            id INTEGER PRIMARY KEY DEFAULT 1,
            data TEXT NOT NULL
        )
    """)
    conn.run(
        "INSERT INTO bot_state (id, data) VALUES (1, :data) ON CONFLICT (id) DO NOTHING",
        data=json.dumps(_DEFAULT_DB)
    )
    conn.close()


def load_db_sync() -> dict:
    conn = get_conn()
    rows = conn.run("SELECT data FROM bot_state WHERE id = 1")
    conn.close()
    db = json.loads(rows[0][0]) if rows else dict(_DEFAULT_DB)
    db.setdefault("participants", {})
    db.setdefault("counter", 0)
    db.setdefault("pending", {})
    db.setdefault("raffle_date", DEFAULT_RAFFLE_DATE)
    db.setdefault("photo_hashes", {})
    return db


def save_db_sync(db: dict):
    conn = get_conn()
    conn.run(
        "UPDATE bot_state SET data = :data WHERE id = 1",
        data=json.dumps(db, ensure_ascii=False)
    )
    conn.close()


def get_next_number(db: dict) -> str:
    """Generate a unique random 4-digit participant number."""
    used = {info.get("number") for info in db["participants"].values()}
    while True:
        number = str(random.randint(1000, 9999))
        if number not in used:
            return number


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
        ["📥 Экспорт Excel"],
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
        db = load_db_sync()

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
    user = update.message.from_user
    user_id = str(user.id)
    lang = context.user_data.get("lang", "ru")

    # If the user sends a menu button while in this state, handle it and stay put
    if update.message.text:
        all_menu_btns = (
            [TEXTS[l]["menu_btn_raffle"] for l in TEXTS] +
            [TEXTS[l]["menu_btn_number"] for l in TEXTS] +
            [TEXTS[l]["menu_btn_status"] for l in TEXTS]
        )
        if update.message.text in all_menu_btns:
            await handle_user_menu(update, context)
            return WAIT_SCREENSHOT
        # Any other text — check if already approved, else ask for photo
        db = load_db_sync()
        if user_id in db["participants"] and db["participants"][user_id].get("approved"):
            number = db["participants"][user_id]["number"]
            await update.message.reply_text(
                txt(lang, "already_registered", number=number),
                parse_mode="Markdown",
                reply_markup=user_menu(lang)
            )
            return ConversationHandler.END
        await update.message.reply_text(txt(lang, "error_photo"))
        return WAIT_SCREENSHOT

    if not update.message.photo:
        await update.message.reply_text(txt(lang, "error_photo"))
        return WAIT_SCREENSHOT

    async with db_lock:
        db = load_db_sync()

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
        save_db_sync(db)

    await update.message.reply_text(
        txt(lang, "got_screenshot"),
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
        f"👤 {escape_markdown(user.full_name or '', version=1)}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 @{escape_markdown(user.username or 'нет', version=1)}\n"
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
    db = load_db_sync()

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

# ─────────────────────────────────────────────
# ADMIN ACTIONS — shared logic called by both menu and slash commands
# ─────────────────────────────────────────────

async def action_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db_lock:
        db = load_db_sync()
    total = len(db["participants"])
    pending = len(db["pending"])
    await update.message.reply_text(
        f"📊 *Статистика акции Tcell 5G*\n\n"
        f"✅ Подтверждённых участников: *{total}*\n"
        f"⏳ Ожидают проверки: *{pending}*\n"
        f"📅 Дата розыгрыша: *{db.get('raffle_date', DEFAULT_RAFFLE_DATE)}*",
        parse_mode="Markdown"
    )


async def send_pending_page(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """Отправляет следующую порцию из PENDING_PAGE_SIZE ещё не показанных скриншотов.
    Уже показанные ID хранятся в user_data — это исключает пропуски, даже если
    админ одобряет/отклоняет заявки между порциями. В конце — кнопка «Показать ещё»."""
    async with db_lock:
        db = load_db_sync()

    shown = context.user_data.setdefault("pending_shown", set())
    remaining = [(uid, info) for uid, info in db["pending"].items() if uid not in shown]

    if not remaining:
        if shown:
            await context.bot.send_message(chat_id=chat_id, text="✅ Все заявки на проверке показаны.")
        else:
            await context.bot.send_message(chat_id=chat_id, text="✅ Нет скриншотов на проверке.")
        return

    batch = remaining[:PENDING_PAGE_SIZE]

    for uid, info in batch:
        shown.add(uid)
        kbd = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{uid}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{uid}"),
        ]])
        caption = (
            f"📸 Скриншот на проверку\n\n"
            f"👤 {info.get('full_name') or ''}\n"
            f"🆔 ID: {uid}\n"
            f"📛 @{info.get('username') or 'нет'}\n"
            f"🌐 Язык: {'Русский' if info.get('lang') == 'ru' else 'Тоҷикӣ'}\n"
            f"🕐 {info.get('timestamp', '')[:16].replace('T', ' ')}"
        )
        sent = False
        if info.get("photo_b64"):
            try:
                photo_bytes = base64.b64decode(info["photo_b64"])
                await context.bot.send_photo(chat_id=chat_id, photo=io.BytesIO(photo_bytes),
                    caption=caption, reply_markup=kbd)
                sent = True
            except Exception as e:
                logging.warning(f"photo_b64 не сработал для {uid}: {e}")
        if not sent and info.get("file_id"):
            try:
                await context.bot.send_photo(chat_id=chat_id, photo=info["file_id"],
                    caption=caption, reply_markup=kbd)
                sent = True
            except Exception as e:
                logging.warning(f"file_id не сработал для {uid}: {e}")
        if not sent:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"📸 Фото недоступно (старая запись)\n\n{caption}",
                reply_markup=kbd)

    left = len(remaining) - len(batch)
    if left > 0:
        show = min(left, PENDING_PAGE_SIZE)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Осталось на проверке: {left}.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"⬇️ Показать ещё {show}", callback_data="pendingmore")
            ]])
        )


async def action_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_user.id
    async with db_lock:
        db = load_db_sync()
    total = len(db["pending"])
    if total == 0:
        await update.message.reply_text("✅ Нет скриншотов на проверке.")
        return
    # сбрасываем список показанных — начинаем просмотр очереди заново
    context.user_data["pending_shown"] = set()
    await update.message.reply_text(
        f"⏳ Скриншотов на проверке: {total}. Показываю по {PENDING_PAGE_SIZE}..."
    )
    await send_pending_page(context, chat_id)


async def action_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_broadcast"] = True
    await update.message.reply_text(
        "✏️ Напишите текст для рассылки всем участникам.\n\n"
        "Поддерживается *жирный*, _курсив_, `код`.\n\n"
        "Для отмены напишите /cancel"
    )


async def action_setdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    async with db_lock:
        db = load_db_sync()
    context.user_data["waiting_date"] = True
    current = db.get("raffle_date", DEFAULT_RAFFLE_DATE)
    await update.message.reply_text(
        f"📅 Текущая дата розыгрыша: *{current}*\n\n"
        "Напишите новую дату в формате ДД.ММ.ГГГГ\n"
        "Например: 15.07.2025\n\n"
        "Для отмены напишите /cancel",
        parse_mode="Markdown"
    )


async def action_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with db_lock:
        db = load_db_sync()
    if not db["participants"]:
        await update.message.reply_text("📭 Нет подтверждённых участников для экспорта.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Участники"

    headers = ["№", "Telegram ID", "Полное имя", "Username", "Язык", "Дата регистрации"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for uid, info in sorted(db["participants"].items(), key=lambda x: int(x[1].get("number", "0"))):
        ws.append([
            info.get("number", ""),
            uid,
            info.get("full_name", ""),
            f"@{info.get('username', '')}" if info.get("username") else "",
            "Русский" if info.get("lang") == "ru" else "Тоҷикӣ",
            info.get("approved_at", "")[:16].replace("T", " "),
        ])

    # Auto-width columns
    for col in ws.columns:
        max_len = max((len(str(cell.value)) if cell.value is not None else 0) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = max_len + 4

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f"tcell_5g_participants_{datetime.now().strftime('%d%m%Y')}.xlsx"
    await context.bot.send_document(
        chat_id=user_id, document=output, filename=filename,
        caption=f"📥 Экспорт участников — {len(db['participants'])} чел.\n{datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )


# ─────────────────────────────────────────────
# SLASH COMMANDS — admin only
# ─────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await action_stats(update, context)

async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await action_pending(update, context)

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await action_broadcast(update, context)

async def cmd_setdate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await action_setdate(update, context)

async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await action_export(update, context)


async def handle_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if update.effective_user.id not in ADMIN_IDS:
        return

    if text == "📊 Статистика":
        await action_stats(update, context)
    elif text == "⏳ На проверке":
        await action_pending(update, context)
    elif text == "📤 Рассылка":
        await action_broadcast(update, context)
    elif text == "📅 Изменить дату":
        await action_setdate(update, context)
    elif text == "📥 Экспорт Excel":
        await action_export(update, context)


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    if context.user_data.get("waiting_broadcast"):
        context.user_data.pop("waiting_broadcast")
        message_text = update.message.text
        async with db_lock:
            db = load_db_sync()
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
            db = load_db_sync()
            db["raffle_date"] = new_date
            save_db_sync(db)
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
            db = load_db_sync()

            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано."
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
            save_db_sync(db)

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
            caption=(query.message.caption or "") + f"\n\n✅ Одобрено. Номер: #{number} | Всего: {total}"
        )

    # ── Отклонение — показать причины ──────────
    elif data.startswith("reject_") and not data.startswith("rejectconfirm_"):
        target_user_id = data[len("reject_"):]

        async with db_lock:
            db = load_db_sync()
            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано."
                )
                return

        await query.edit_message_caption(
            caption=(query.message.caption or "") + "\n\n❓ Укажите причину отклонения:",
            reply_markup=reject_reason_keyboard(target_user_id)
        )

    # ── Отклонение — подтверждение с причиной ──
    elif data.startswith("rejectconfirm_"):
        parts = data.split("_", 2)  # ["rejectconfirm", uid, reason_code]
        if len(parts) != 3:
            return
        _, target_user_id, reason_code = parts

        async with db_lock:
            db = load_db_sync()

            if target_user_id not in db["pending"]:
                await query.edit_message_caption(
                    caption=(query.message.caption or "") + "\n\n⚠️ Уже обработано."
                )
                return

            pending_info = db["pending"].pop(target_user_id)
            lang = pending_info.get("lang", "ru")
            save_db_sync(db)

        reason_key = f"rejected_{reason_code}"
        msg = TEXTS[lang].get(reason_key) or TEXTS[lang].get("rejected_other") or TEXTS[lang]["rejected_no5g"]

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
            caption=(query.message.caption or "") + f"\n\n❌ Отклонено. Причина: {reason_label}"
        )


async def pending_more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка «Показать ещё» под порцией скриншотов на проверке."""
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("⛔ У вас нет прав.", show_alert=True)
        return
    await query.answer()
    # убираем кнопку у старого сообщения, чтобы не нажимали повторно
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    await send_pending_page(context, query.message.chat_id)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("waiting_broadcast", None)
    context.user_data.pop("waiting_date", None)
    await update.message.reply_text(
        "Отменено.",
        reply_markup=admin_menu() if update.effective_user.id in ADMIN_IDS else ReplyKeyboardRemove()
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────

async def daily_backup(context: ContextTypes.DEFAULT_TYPE):
    """Send participants backup to all admins at 10:00 AM Dushanbe (UTC+5)."""
    db = load_db_sync()
    backup_data = json.dumps(db, ensure_ascii=False, indent=2).encode("utf-8")
    total = len(db["participants"])
    tz_dushanbe = timezone(timedelta(hours=5))
    now_str = datetime.now(tz_dushanbe).strftime("%d.%m.%Y %H:%M")
    filename = f"participants_backup_{datetime.now(tz_dushanbe).strftime('%Y%m%d')}.json"
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_document(
                chat_id=admin_id,
                document=io.BytesIO(backup_data),
                filename=filename,
                caption=(
                    f"🗄 *Ежедневный бэкап базы данных*\n\n"
                    f"✅ Участников: *{total}*\n"
                    f"📅 {now_str} (UTC+5)"
                ),
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.error(f"Ошибка отправки бэкапа админу {admin_id}: {e}")



# ─────────────────────────────────────────────
# ЗАПУСК
# ─────────────────────────────────────────────

async def post_init(application: Application):
    """Initialize DB, set slash commands, and schedule jobs."""
    init_db_sync()

    # Admin slash commands
    commands = [
        BotCommand("stats",      "Статистика акции"),
        BotCommand("pending",    "Скриншоты на проверке"),
        BotCommand("broadcast",  "Рассылка участникам"),
        BotCommand("setdate",    "Изменить дату розыгрыша"),
        BotCommand("export",     "Экспорт участников XLSX"),
    ]
    for admin_id in ADMIN_IDS:
        try:
            await application.bot.set_my_commands(
                commands, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as e:
            logging.warning(f"Не удалось установить команды для админа {admin_id}: {e}")

    # Daily backup: 10:00 AM Dushanbe = 05:00 UTC
    application.job_queue.run_daily(
        daily_backup,
        time=time(5, 0, 0, tzinfo=timezone.utc),
        name="daily_backup"
    )


def main():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO
    )

    persistence = PicklePersistence(filepath=PERSISTENCE_FILE)
    app = Application.builder().token(BOT_TOKEN).persistence(persistence).post_init(post_init).build()

    all_user_btns = (
        [v["menu_btn_raffle"] for v in TEXTS.values()] +
        [v["menu_btn_number"] for v in TEXTS.values()] +
        [v["menu_btn_status"] for v in TEXTS.values()]
    )
    admin_btns = ["📊 Статистика", "⏳ На проверке", "📤 Рассылка", "📅 Изменить дату", "📥 Экспорт Excel"]

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
    app.add_handler(CommandHandler("stats",     cmd_stats))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("broadcast", cmd_broadcast))
    app.add_handler(CommandHandler("setdate",   cmd_setdate))
    app.add_handler(CommandHandler("export",    cmd_export))
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve_|reject_|rejectconfirm_)"))
    app.add_handler(CallbackQueryHandler(pending_more, pattern="^pendingmore$"))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(re.escape(b) for b in all_user_btns)), handle_user_menu))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("|".join(re.escape(b) for b in admin_btns)), handle_admin_menu))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_admin_input))
    # Fallback: фото от пользователей вне ConversationHandler (после отклонения)
    app.add_handler(MessageHandler(filters.PHOTO, receive_screenshot))

    print("🤖 Бот Tcell 5G запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

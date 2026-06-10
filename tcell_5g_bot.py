"""
Tcell 5G Campaign Bot
Двуязычный бот (рус/тадж) для акции подключения 5G
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
# НАСТРОЙКИ — заполни перед запуском
# ─────────────────────────────────────────────
BOT_TOKEN = "8996137532:AAFK4n4MxYji5sXPWgyAxlPzs4mjEHXAkfI"         # токен от @BotFather
ADMIN_IDS = [1461029743]                    # Telegram ID администраторов
COVERAGE_MAP_FILE = "coverage_map.jpg"    # путь к картинке карты 5G покрытия
DB_FILE = "participants.json"             # файл-база участников

# ─────────────────────────────────────────────
# СОСТОЯНИЯ РАЗГОВОРА
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
            "5. Сделайте скриншот экрана телефона с видимым значком 5G\n\n"
            "📤 Отправьте скриншот прямо сюда!"
        ),
        "wait_screenshot": "⏳ Жду ваш скриншот...",
        "got_screenshot": (
            "✅ Скриншот получен! Передаю на проверку администратору.\n\n"
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
            "Пожалуйста, попробуйте ещё раз — отправьте новый скриншот 👇"
        ),
        "already_registered": (
            "ℹ️ Вы уже зарегистрированы в акции!\n\n"
            "Ваш номер участника: *#{number}*\n\n"
            "Следите за розыгрышем в нашем канале 🎁"
        ),
        "pending": (
            "⏳ Ваш скриншот уже на проверке у администратора.\n"
            "Пожалуйста, подождите немного."
        ),
        "error_photo": "❗ Пожалуйста, отправьте именно фото (скриншот), а не файл или текст.",
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
            "4. Боварӣ ҳосил кунед, ки дар қисми болои экран аломати *5G* намоён аст\n"
            "5. Аз экрани телефонатон бо аломати 5G скриншот гиред\n\n"
            "📤 Скриншотро ҳамин ҷо фиристед!"
        ),
        "wait_screenshot": "⏳ Скриншоти шуморо интизорам...",
        "got_screenshot": (
            "✅ Скриншот гирифта шуд! Барои тафтиш ба маъмур мефиристам.\n\n"
            "Баъди тафтиши скриншот, рақами беназири иштирокчии шумо дода мешавад. "
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
            "Лутфан дубора кӯшиш кунед — скриншоти наверо фиристед 👇"
        ),
        "already_registered": (
            "ℹ️ Шумо аллакай дар акция бақайд гирифта шудед!\n\n"
            "Рақами иштирокчии шумо: *#{number}*\n\n"
            "Қуръакаширо дар канали мо пайгирӣ кунед 🎁"
        ),
        "pending": (
            "⏳ Скриншоти шумо аллакай назди маъмур барои тафтиш аст.\n"
            "Лутфан каме интизор шавед."
        ),
        "error_photo": "❗ Лутфан акс (скриншот) фиристед, на файл ё матн.",
    }
}

# ─────────────────────────────────────────────
# БАЗА ДАННЫХ (JSON-файл)
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
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇹🇯 Тоҷикӣ", callback_data="lang_tj"),
        ]
    ])


def get_user_lang(context: ContextTypes.DEFAULT_TYPE) -> str:
    return context.user_data.get("lang", "ru")


def t(context, key: str, **kwargs) -> str:
    lang = get_user_lang(context)
    text = TEXTS[lang].get(key, TEXTS["ru"].get(key, key))
    for k, v in kwargs.items():
        text = text.replace(f"{{{k}}}", str(v))
    return text


# ─────────────────────────────────────────────
# ХЕНДЛЕРЫ
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Приветствие + выбор языка"""
    await update.message.reply_text(
        "🌐 Выберите язык / Забонро интихоб кунед:",
        reply_markup=lang_keyboard()
    )
    return CHOOSE_LANG


async def choose_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка выбора языка"""
    query = update.callback_query
    await query.answer()

    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang

    user_id = str(query.from_user.id)
    db = load_db()

    # Уже зарегистрирован и подтверждён
    if user_id in db["participants"] and db["participants"][user_id].get("approved"):
        number = db["participants"][user_id]["number"]
        await query.edit_message_text(
            t(context, "already_registered", number=number),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    # Уже отправил скриншот — ожидает проверки
    if user_id in db["pending"]:
        await query.edit_message_text(t(context, "pending"))
        return ConversationHandler.END

    # Приветственное сообщение
    await query.edit_message_text(t(context, "welcome"))

    # Карта покрытия
    try:
        with open(COVERAGE_MAP_FILE, "rb") as photo:
            await query.message.reply_photo(
                photo=photo,
                caption=t(context, "map_caption"),
                parse_mode="Markdown"
            )
    except FileNotFoundError:
        # Если файл карты не найден — шлём текст-заглушку
        await query.message.reply_text(
            t(context, "map_caption"),
            parse_mode="Markdown"
        )

    await query.message.reply_text(t(context, "wait_screenshot"))
    return WAIT_SCREENSHOT


async def receive_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение скриншота от пользователя"""
    if not update.message.photo:
        await update.message.reply_text(t(context, "error_photo"))
        return WAIT_SCREENSHOT

    user = update.message.from_user
    user_id = str(user.id)
    db = load_db()

    # Двойная проверка
    if user_id in db["participants"] and db["participants"][user_id].get("approved"):
        number = db["participants"][user_id]["number"]
        await update.message.reply_text(
            t(context, "already_registered", number=number),
            parse_mode="Markdown"
        )
        return ConversationHandler.END

    if user_id in db["pending"]:
        await update.message.reply_text(t(context, "pending"))
        return WAIT_SCREENSHOT

    # Сохраняем в pending
    lang = get_user_lang(context)
    file_id = update.message.photo[-1].file_id
    db["pending"][user_id] = {
        "user_id": user_id,
        "username": user.username or "",
        "full_name": user.full_name,
        "lang": lang,
        "file_id": file_id,
        "timestamp": datetime.now().isoformat(),
    }
    save_db(db)

    await update.message.reply_text(t(context, "got_screenshot"))

    # Пересылаем каждому админу
    admin_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{user_id}"),
        ]
    ])

    admin_caption = (
        f"📸 *Новый скриншот на проверку*\n\n"
        f"👤 Пользователь: {user.full_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"📛 Username: @{user.username or 'нет'}\n"
        f"🌐 Язык: {'Русский' if lang == 'ru' else 'Тоҷикӣ'}\n"
        f"🕐 Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=file_id,
                caption=admin_caption,
                parse_mode="Markdown",
                reply_markup=admin_keyboard
            )
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение админу {admin_id}: {e}")

    return WAIT_SCREENSHOT


async def admin_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Админ одобряет или отклоняет скриншот"""
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
            caption=query.message.caption + "\n\n⚠️ Уже обработано другим администратором.",
            parse_mode="Markdown"
        )
        return

    pending_info = db["pending"].pop(target_user_id)
    lang = pending_info.get("lang", "ru")
    context.user_data["lang"] = lang  # для t()

    if action == "approve":
        number = get_next_number(db)
        db["participants"][target_user_id] = {
            **pending_info,
            "number": number,
            "approved": True,
            "approved_at": datetime.now().isoformat(),
        }
        save_db(db)

        # Уведомляем пользователя
        msg = TEXTS[lang]["approved"].replace("{number}", number)
        try:
            await context.bot.send_message(
                chat_id=int(target_user_id),
                text=msg,
                parse_mode="Markdown"
            )
        except Exception as e:
            logging.warning(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await query.edit_message_caption(
            caption=query.message.caption + f"\n\n✅ *Одобрено* администратором. Номер участника: *#{number}*",
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
            logging.warning(f"Не удалось уведомить пользователя {target_user_id}: {e}")

        await query.edit_message_caption(
            caption=query.message.caption + "\n\n❌ *Отклонено* администратором.",
            parse_mode="Markdown"
        )


async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Статистика для администратора /stats"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    db = load_db()
    total = len(db["participants"])
    pending = len(db["pending"])

    await update.message.reply_text(
        f"📊 *Статистика акции Tcell 5G*\n\n"
        f"✅ Подтверждённых участников: *{total}*\n"
        f"⏳ Ожидают проверки: *{pending}*\n"
        f"🔢 Следующий номер: *{str(db['counter'] + 1).zfill(3)}*",
        parse_mode="Markdown"
    )


async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Рассылка всем участникам /broadcast текст"""
    if update.effective_user.id not in ADMIN_IDS:
        return

    if not context.args:
        await update.message.reply_text("Использование: /broadcast <текст сообщения>")
        return

    message_text = " ".join(context.args)
    db = load_db()
    success, failed = 0, 0

    for uid in db["participants"]:
        try:
            await context.bot.send_message(chat_id=int(uid), text=message_text)
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📤 Рассылка завершена.\n✅ Отправлено: {success}\n❌ Ошибок: {failed}"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Операция отменена. Нажмите /start чтобы начать заново.")
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
                MessageHandler(filters.ALL & ~filters.COMMAND, receive_screenshot),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_user=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(admin_decision, pattern="^(approve|reject)_"))
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", broadcast))

    print("🤖 Бот Tcell 5G запущен!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

import os
import logging
from datetime import date, datetime
from dotenv import load_dotenv

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db
import claude_client as ai

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Conversation states
(
    SETUP_NAME, SETUP_AGE, SETUP_WEIGHT, SETUP_CALORIES,
    MEMBER_NAME, MEMBER_AGE, MEMBER_WEIGHT, MEMBER_CALORIES,
    SET_ALLERGIES, SET_DISLIKES,
    EXCLUDE_TODAY,
    FRIDGE_INPUT,
    EDIT_NAME, EDIT_AGE, EDIT_WEIGHT, EDIT_CALORIES,
) = range(16)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🍽 Рецепты на сегодня", "🧊 Рецепты из холодильника"],
        ["👨‍👩‍👧 Члены семьи", "✏️ Изменить параметры"],
        ["🚫 Исключить продукт сегодня", "📋 Аллергии и нелюбимые"],
    ],
    resize_keyboard=True,
)

# Keyboard shown inside the family section (text buttons replaced by inline, kept for fallback)



# ── Helpers ──────────────────────────────────────────────────────────────────

async def send_long(update: Update, text: str):
    MAX = 4000
    for i in range(0, len(text), MAX):
        await update.message.reply_text(text[i:i + MAX], parse_mode="HTML")


async def require_profile(update: Update) -> bool:
    user = await db.get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text(
            "Сначала настройте профиль командой /start или /setup."
        )
        return False
    return True


# ── /start ────────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    existing = await db.get_user(update.effective_user.id)
    if existing:
        await update.message.reply_text(
            f"С возвращением, {existing['name']}! 👋\nВыберите действие:",
            reply_markup=MAIN_KEYBOARD,
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Привет! Я бот-диетолог 🥗\n\n"
        "Давайте настроим ваш профиль.\n"
        "Как вас зовут?"
    )
    return SETUP_NAME


async def setup_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Сколько вам лет?")
    return SETUP_AGE


async def setup_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["age"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число, например: 30")
        return SETUP_AGE
    await update.message.reply_text("Ваш вес (кг)?")
    return SETUP_WEIGHT


async def setup_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["weight"] = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число, например: 65.5")
        return SETUP_WEIGHT
    await update.message.reply_text("Ваша цель по калориям в день (ккал)?")
    return SETUP_CALORIES


async def setup_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cal = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число, например: 1800")
        return SETUP_CALORIES

    uid = update.effective_user.id
    d = context.user_data
    await db.upsert_user(uid, d["name"], d["age"], d["weight"], cal)
    await update.message.reply_text(
        f"Профиль сохранён! ✅\n"
        f"Имя: {d['name']}, Возраст: {d['age']} лет, Вес: {d['weight']} кг, Калории: {cal} ккал\n\n"
        "Теперь вы можете добавить членов семьи или сразу запросить рецепты.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── /setup (re-enter own params) ─────────────────────────────────────────────

async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Как вас зовут?")
    return SETUP_NAME


# ── Edit params ───────────────────────────────────────────────────────────────

def _edit_params_keyboard(user: dict, members: list[dict]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(
        f"👑 {user['name']} · {user['age']} лет · {user['weight']} кг · {user['calories']} ккал",
        callback_data="edit_self"
    )]]
    for m in members:
        buttons.append([InlineKeyboardButton(
            f"👤 {m['name']} · {m['age']} лет · {m['weight']} кг · {m['calories']} ккал",
            callback_data=f"edit_member_{m['id']}"
        )])
    return InlineKeyboardMarkup(buttons)


async def edit_params_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    uid = update.effective_user.id
    user = await db.get_user(uid)
    members = await db.get_family_members(uid)
    await update.message.reply_text(
        "✏️ *Изменить параметры*\n\nВыберите, чьи параметры хотите изменить:",
        parse_mode="Markdown",
        reply_markup=_edit_params_keyboard(user, members),
    )


async def edit_params_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "edit_self":
        context.user_data["editing_member_id"] = "self"
        await query.edit_message_text("Введите новое имя (или «-» чтобы не менять):")
    elif data.startswith("edit_member_"):
        member_id = int(data.split("_")[-1])
        context.user_data["editing_member_id"] = member_id
        await query.edit_message_text("Введите новое имя (или «-» чтобы не менять):")
    return EDIT_NAME


async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    context.user_data["edit_name"] = None if val == "-" else val
    await update.message.reply_text("Возраст (или «-»):")
    return EDIT_AGE


async def edit_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if val != "-":
        try:
            context.user_data["edit_age"] = int(val)
        except ValueError:
            await update.message.reply_text("Введите число или «-»:")
            return EDIT_AGE
    else:
        context.user_data["edit_age"] = None
    await update.message.reply_text("Вес в кг (или «-»):")
    return EDIT_WEIGHT


async def edit_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip().replace(",", ".")
    if val != "-":
        try:
            context.user_data["edit_weight"] = float(val)
        except ValueError:
            await update.message.reply_text("Введите число или «-»:")
            return EDIT_WEIGHT
    else:
        context.user_data["edit_weight"] = None
    await update.message.reply_text("Калории в день (или «-»):")
    return EDIT_CALORIES


async def edit_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val = update.message.text.strip()
    if val != "-":
        try:
            context.user_data["edit_calories"] = int(val)
        except ValueError:
            await update.message.reply_text("Введите число или «-»:")
            return EDIT_CALORIES
    else:
        context.user_data["edit_calories"] = None

    uid = update.effective_user.id
    d = context.user_data
    mid = d.get("editing_member_id")

    if mid == "self":
        current = await db.get_user(uid)
        await db.upsert_user(
            uid,
            d["edit_name"] or current["name"],
            d["edit_age"] or current["age"],
            d["edit_weight"] or current["weight"],
            d["edit_calories"] or current["calories"],
        )
    else:
        members = await db.get_family_members(uid)
        current = next(m for m in members if m["id"] == mid)
        await db.update_family_member(
            mid,
            d["edit_name"] or current["name"],
            d["edit_age"] or current["age"],
            d["edit_weight"] or current["weight"],
            d["edit_calories"] or current["calories"],
        )

    user = await db.get_user(uid)
    members = await db.get_family_members(uid)
    await update.message.reply_text(
        "✅ Параметры обновлены!\n\nВыберите ещё кого-то или вернитесь в меню:",
        reply_markup=_edit_params_keyboard(user, members),
    )
    return ConversationHandler.END


# ── Family members ────────────────────────────────────────────────────────────

def _family_keyboard(user: dict, members: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    # Сам пользователь (без кнопки удаления)
    buttons.append([
        InlineKeyboardButton(
            f"👑 {user['name']} · {user['age']} лет · {user['weight']} кг · {user['calories']} ккал",
            callback_data="member_info_self"
        )
    ])
    for m in members:
        buttons.append([
            InlineKeyboardButton(
                f"👤 {m['name']} · {m['age']} лет · {m['weight']} кг · {m['calories']} ккал",
                callback_data=f"member_info_{m['id']}"
            )
        ])
        buttons.append([
            InlineKeyboardButton(f"🗑 Удалить {m['name']}", callback_data=f"del_member_{m['id']}")
        ])
    buttons.append([InlineKeyboardButton("➕ Добавить члена семьи", callback_data="add_member")])
    return InlineKeyboardMarkup(buttons)


async def family_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    uid = update.effective_user.id
    user = await db.get_user(uid)
    members = await db.get_family_members(uid)

    text = "👨‍👩‍👧 *Члены семьи*\n\nЗдесь отображаются все, для кого готовите."
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=_family_keyboard(user, members),
    )


async def family_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    data = query.data

    if data.startswith("del_member_"):
        member_id = int(data.split("_")[-1])
        await db.delete_family_member(uid, member_id)
        user = await db.get_user(uid)
        members = await db.get_family_members(uid)
        await query.edit_message_text(
            "👨‍👩‍👧 *Члены семьи*\n\nЗдесь отображаются все, для кого готовите.",
            parse_mode="Markdown",
            reply_markup=_family_keyboard(user, members),
        )

    elif data == "add_member":
        await query.edit_message_text("Введите имя нового члена семьи:", reply_markup=None)
        context.user_data["adding_member_inline"] = True
        return MEMBER_NAME


async def add_member_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    await update.message.reply_text("Имя нового члена семьи?")
    return MEMBER_NAME


async def member_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["m_name"] = update.message.text.strip()
    await update.message.reply_text("Возраст?")
    return MEMBER_AGE


async def member_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["m_age"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число.")
        return MEMBER_AGE
    await update.message.reply_text("Вес (кг)?")
    return MEMBER_WEIGHT


async def member_weight(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["m_weight"] = float(update.message.text.strip().replace(",", "."))
    except ValueError:
        await update.message.reply_text("Введите число.")
        return MEMBER_WEIGHT
    await update.message.reply_text("Цель по калориям (ккал/день)?")
    return MEMBER_CALORIES


async def member_calories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cal = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("Введите число.")
        return MEMBER_CALORIES

    uid = update.effective_user.id
    d = context.user_data
    await db.add_family_member(uid, d["m_name"], d["m_age"], d["m_weight"], cal)
    user = await db.get_user(uid)
    members = await db.get_family_members(uid)
    await update.message.reply_text(
        f"✅ {d['m_name']} добавлен(а)!\n\n👨‍👩‍👧 *Члены семьи*",
        parse_mode="Markdown",
        reply_markup=_family_keyboard(user, members),
    )
    return ConversationHandler.END




# ── Allergies & dislikes ──────────────────────────────────────────────────────

async def allergies_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    kb = ReplyKeyboardMarkup(
        [["✏️ Изменить аллергии"], ["✏️ Изменить нелюбимые продукты"], ["🔙 Назад"]],
        resize_keyboard=True,
    )
    await update.message.reply_text("Что хотите изменить?", reply_markup=kb)


async def set_allergies_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    await update.message.reply_text(
        "Введите продукты с аллергией через запятую (или 'нет' для сброса):\n"
        "Пример: молоко, орехи, глютен",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SET_ALLERGIES


async def set_allergies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    allergies = [] if text == "нет" else [x.strip() for x in text.split(",") if x.strip()]
    await db.update_allergies(update.effective_user.id, allergies)
    await update.message.reply_text(
        f"✅ Аллергии обновлены: {', '.join(allergies) or 'нет'}",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


async def set_dislikes_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    await update.message.reply_text(
        "Введите нелюбимые продукты через запятую (или 'нет' для сброса):\n"
        "Пример: капуста, рыба, лук",
        reply_markup=ReplyKeyboardRemove(),
    )
    return SET_DISLIKES


async def set_dislikes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()
    dislikes = [] if text == "нет" else [x.strip() for x in text.split(",") if x.strip()]
    await db.update_dislikes(update.effective_user.id, dislikes)
    await update.message.reply_text(
        f"✅ Нелюбимые продукты обновлены: {', '.join(dislikes) or 'нет'}",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Exclude today ─────────────────────────────────────────────────────────────

async def exclude_today_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    today = date.today().isoformat()
    current = await db.get_daily_exclusions(update.effective_user.id, today)
    msg = "Введите продукты, которые хотите исключить сегодня (через запятую).\n"
    if current:
        msg += f"Уже исключены: {', '.join(current)}\n"
    msg += "Пример: курица, картофель"
    await update.message.reply_text(msg, reply_markup=ReplyKeyboardRemove())
    return EXCLUDE_TODAY


async def exclude_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today = date.today().isoformat()
    items = [x.strip() for x in update.message.text.split(",") if x.strip()]
    for item in items:
        await db.add_daily_exclusion(uid, item, today)
    await update.message.reply_text(
        f"✅ На сегодня исключено: {', '.join(items)}\nБот предложит замену.",
        reply_markup=MAIN_KEYBOARD,
    )
    return ConversationHandler.END


# ── Daily recipes ─────────────────────────────────────────────────────────────

async def daily_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    uid = update.effective_user.id
    await update.message.reply_text("⏳ Генерирую рецепты на сегодня, подождите немного...")

    user = await db.get_user(uid)
    members = await db.get_family_members(uid)
    exclusions = await db.get_daily_exclusions(uid, date.today().isoformat())

    try:
        result = await ai.generate_daily_recipes(user, members, exclusions)
        await send_long(update, result)
    except Exception as e:
        logger.error(f"Error generating recipes: {e}", exc_info=True)
        await update.message.reply_text(f"Ошибка: {e}")


# ── Fridge recipes ────────────────────────────────────────────────────────────

async def fridge_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_profile(update):
        return
    await update.message.reply_text(
        "Напишите, что есть у вас в холодильнике (через запятую или списком):\n"
        "Пример: куриная грудка, яйца, помидоры, огурцы, сметана, гречка",
        reply_markup=ReplyKeyboardRemove(),
    )
    return FRIDGE_INPUT


async def fridge_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    contents = update.message.text.strip()
    await update.message.reply_text("⏳ Подбираю рецепты из того, что есть...")

    user = await db.get_user(uid)
    members = await db.get_family_members(uid)
    exclusions = await db.get_daily_exclusions(uid, date.today().isoformat())

    try:
        result = await ai.generate_fridge_recipes(user, members, exclusions, contents)
        await send_long(update, result)
    except Exception as e:
        logger.error(f"Error generating fridge recipes: {e}")
        await update.message.reply_text("Произошла ошибка. Попробуйте позже.")

    await update.message.reply_text("Что ещё хотите сделать?", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


# ── Cancel ────────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отменено.", reply_markup=MAIN_KEYBOARD)
    return ConversationHandler.END


async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Главное меню:", reply_markup=MAIN_KEYBOARD)


# ── Scheduled daily delivery ──────────────────────────────────────────────────

async def scheduled_daily_recipes(app: Application):
    user_ids = await db.get_all_user_ids()
    today = date.today().isoformat()

    for uid in user_ids:
        try:
            user = await db.get_user(uid)
            members = await db.get_family_members(uid)
            exclusions = await db.get_daily_exclusions(uid, today)
            result = await ai.generate_daily_recipes(user, members, exclusions)

            MAX = 4000
            for i in range(0, len(result), MAX):
                await app.bot.send_message(chat_id=uid, text=result[i:i + MAX])
        except Exception as e:
            logger.error(f"Scheduled recipes error for {uid}: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def build_app() -> Application:
    async def post_init(application: Application):
        await db.init_db()
        scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        scheduler.add_job(
            scheduled_daily_recipes,
            trigger="cron",
            hour=8,
            minute=0,
            args=[application],
        )
        scheduler.start()
        logger.info("Bot started")

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    setup_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("setup", setup_command),
        ],
        states={
            SETUP_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_name)],
            SETUP_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_age)],
            SETUP_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_weight)],
            SETUP_CALORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, setup_calories)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    member_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^➕ Добавить члена семьи$"), add_member_start),
            CallbackQueryHandler(family_callback, pattern="^add_member$"),
        ],
        states={
            MEMBER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_name)],
            MEMBER_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_age)],
            MEMBER_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_weight)],
            MEMBER_CALORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_calories)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    allergies_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✏️ Изменить аллергии$"), set_allergies_start),
        ],
        states={
            SET_ALLERGIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_allergies)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    dislikes_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^✏️ Изменить нелюбимые продукты$"), set_dislikes_start),
        ],
        states={
            SET_DISLIKES: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_dislikes)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    exclude_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🚫 Исключить продукт сегодня$"), exclude_today_start),
        ],
        states={
            EXCLUDE_TODAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, exclude_today)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    fridge_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🧊 Рецепты из холодильника$"), fridge_start),
        ],
        states={
            FRIDGE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, fridge_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(setup_conv)
    app.add_handler(member_conv)
    app.add_handler(allergies_conv)
    app.add_handler(dislikes_conv)
    app.add_handler(exclude_conv)
    app.add_handler(fridge_conv)

    edit_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(edit_params_callback, pattern="^edit_(self|member_\\d+)$")],
        states={
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
            EDIT_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_age)],
            EDIT_WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_weight)],
            EDIT_CALORIES: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_calories)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(edit_conv)
    app.add_handler(CallbackQueryHandler(family_callback, pattern="^del_member_"))
    app.add_handler(MessageHandler(filters.Regex("^🍽 Рецепты на сегодня$"), daily_recipes))
    app.add_handler(MessageHandler(filters.Regex("^👨‍👩‍👧 Члены семьи$"), family_menu))
    app.add_handler(MessageHandler(filters.Regex("^✏️ Изменить параметры$"), edit_params_menu))
    app.add_handler(MessageHandler(filters.Regex("^📋 Аллергии и нелюбимые$"), allergies_menu))
    app.add_handler(MessageHandler(filters.Regex("^🔙 Назад$"), back))

    return app


if __name__ == "__main__":
    build_app().run_polling(allowed_updates=Update.ALL_TYPES)

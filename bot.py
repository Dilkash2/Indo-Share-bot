
import os
import sqlite3
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("8874481251:AAGvfjfEbuGBj-cFcwieBbV7v5JDM2Mlyo0")

# Tumhari GitHub Pages Mini App
MINI_APP_URL = "https://dilkash2.github.io/Indo-Share-bot/"

# Apna Telegram numeric user ID yahan baad mein set karna
ADMIN_ID = int(os.getenv("8874481251", "0"))

DB_NAME = "files.db"


# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            file_id TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def save_file(code, file_id):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO files (code, file_id) VALUES (?, ?)",
        (code, file_id)
    )

    conn.commit()
    conn.close()


def get_file(code):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        "SELECT file_id FROM files WHERE code = ?",
        (code,)
    )

    result = cur.fetchone()

    conn.close()

    if result:
        return result[0]

    return None


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    args = context.args

    # Normal /start
    if not args:

        keyboard = [
            [
                InlineKeyboardButton(
                    "📤 UPLOAD FILE",
                    callback_data="upload_info"
                )
            ]
        ]

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "File link open karne ke liye apna file link use karein.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        return

    # File link
    code = args[0]

    file_id = get_file(code)

    if not file_id:
        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Verify & Get File",
                web_app=WebAppInfo(
                    url=f"{MINI_APP_URL}?file={code}"
                )
            )
        ]
    ]

    await update.message.reply_text(
        "📁 File Ready!\n\n"
        "File lene ke liye verification complete karein.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# UPLOAD
# =========================

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Sirf admin is command ka use kar sakta hai."
        )

        return

    await update.message.reply_text(
        "📤 Ab mujhe koi file bhejo.\n\n"
        "Main uska unique download link bana dunga."
    )


# =========================
# FILE RECEIVER
# =========================

async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    telegram_file_id = None

    # Document
    if update.message.document:
        telegram_file_id = update.message.document.file_id

    # Video
    elif update.message.video:
        telegram_file_id = update.message.video.file_id

    # Audio
    elif update.message.audio:
        telegram_file_id = update.message.audio.file_id

    # Photo
    elif update.message.photo:
        telegram_file_id = update.message.photo[-1].file_id

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ Ye file type supported nahi hai."
        )
        return

    # Unique code
    code = f"file_{update.message.message_id}"

    save_file(code, telegram_file_id)

    bot_username = context.bot.username

    link = f"https://t.me/{bot_username}?start={code}"

    await update.message.reply_text(
        "✅ File successfully saved!\n\n"
        f"🔗 File Link:\n{link}\n\n"
        "Is link ko apne Telegram channel mein post kar sakte ho."
    )


# =========================
# GET FILE
# =========================

async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        return

    code = context.args[0]

    file_id = get_file(code)

    if not file_id:
        await update.message.reply_text(
            "❌ File nahi mili."
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "🚀 Verify & Get File",
                web_app=WebAppInfo(
                    url=f"{MINI_APP_URL}?file={code}"
                )
            )
        ]
    ]

    await update.message.reply_text(
        "🔐 Verification required.\n\n"
        "Verification complete karke file receive karein.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# ADMIN HELP
# =========================

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👑 Admin Commands\n\n"
        "/upload - File upload karein\n"
        "/start - Bot start\n"
    )


# =========================
# MAIN
# =========================

def main():

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN environment variable missing hai."
        )

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("upload", upload_command)
    )

    app.add_handler(
        CommandHandler("admin", admin_command)
    )

    app.add_handler(
        MessageHandler(
            filters.Document.ALL |
            filters.VIDEO |
            filters.AUDIO |
            filters.PHOTO,
            receive_file
        )
    )

    print("🤖 Indo Share Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()

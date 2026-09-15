import os
import sqlite3
import asyncio

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError


# =========================
# SETTINGS
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")

MINI_APP_URL = "https://dilkash2.github.io/Indo-Share-bot/"

ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

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
        "INSERT OR REPLACE INTO files (code, file_id) VALUES (?, ?)",
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

    if not update.message:
        return

    args = context.args

    if not args:
        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 File lene ke liye channel se file link open karein."
        )
        return

    code = args[0]

    file_id = get_file(code)

    if not file_id:
        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )
        return

    # IMPORTANT:
    # Reply keyboard Web App is used because
    # Telegram.WebApp.sendData() works with
    # Keyboard Button Mini Apps.

    web_app_button = KeyboardButton(
        text="👀 Watch Ad & Unlock",
        web_app=WebAppInfo(
            url=f"{MINI_APP_URL}?file={code}"
        )
    )

    keyboard = ReplyKeyboardMarkup(
        [[web_app_button]],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await update.message.reply_text(
        "🔐 One quick step\n\n"
        "👀 Watch the short ad and complete verification.\n\n"
        "Then your file will be sent automatically.",
        reply_markup=keyboard
    )


# =========================
# UPLOAD COMMAND
# =========================

async def upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text(
            "❌ Sirf admin file upload kar sakta hai."
        )
        return

    await update.message.reply_text(
        "📤 Ab mujhe file bhejo.\n\n"
        "Main uska unique link bana dunga."
    )


# =========================
# RECEIVE FILE
# =========================

async def receive_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message:
        return

    telegram_file_id = None

    if update.message.document:
        telegram_file_id = update.message.document.file_id

    elif update.message.video:
        telegram_file_id = update.message.video.file_id

    elif update.message.audio:
        telegram_file_id = update.message.audio.file_id

    elif update.message.photo:
        telegram_file_id = update.message.photo[-1].file_id

    if not telegram_file_id:
        await update.message.reply_text(
            "❌ Ye file type supported nahi hai."
        )
        return

    code = f"file_{update.message.message_id}"

    save_file(code, telegram_file_id)

    bot_username = context.bot.username

    link = f"https://t.me/{bot_username}?start={code}"

    await update.message.reply_text(
        "✅ FILE SAVED SUCCESSFULLY!\n\n"
        f"🔗 File Link:\n{link}\n\n"
        "Is link ko Telegram channel mein post kar sakte ho."
    )


# =========================
# WEB APP DATA
# =========================

async def web_app_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.web_app_data:
        return

    code = update.message.web_app_data.data.strip()

    if not code:
        await update.message.reply_text(
            "❌ File code nahi mila."
        )
        return

    file_id = get_file(code)

    if not file_id:
        await update.message.reply_text(
            "❌ File nahi mili ya link expire ho gaya."
        )
        return

    user_id = update.effective_user.id

    # Remove the Web App keyboard
    await update.message.reply_text(
        "📤 File sending...",
        reply_markup=ReplyKeyboardRemove()
    )

    sent_message = None

    # Try as document
    try:
        sent_message = await context.bot.send_document(
            chat_id=user_id,
            document=file_id
        )
    except TelegramError:
        pass

    # Try as video
    if sent_message is None:
        try:
            sent_message = await context.bot.send_video(
                chat_id=user_id,
                video=file_id
            )
        except TelegramError:
            pass

    # Try as audio
    if sent_message is None:
        try:
            sent_message = await context.bot.send_audio(
                chat_id=user_id,
                audio=file_id
            )
        except TelegramError:
            pass

    # Try as photo
    if sent_message is None:
        try:
            sent_message = await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id
            )
        except TelegramError:
            pass

    if sent_message is None:
        await update.message.reply_text(
            "❌ File send nahi ho paayi.\n\n"
            "Admin se file ko dobara upload karne ko kahen."
        )
        return

    await update.message.reply_text(
        "✅ File successfully sent!\n\n"
        "⚠️ Is file ko apne Saved Messages mein "
        "forward/save kar lena.\n\n"
        "🗑️ File 90 seconds ke baad automatically delete ho jayegi."
    )

    # Delete the actual file message after 90 seconds
    await asyncio.sleep(90)

    try:
        await context.bot.delete_message(
            chat_id=user_id,
            message_id=sent_message.message_id
        )
    except TelegramError:
        pass


# =========================
# ADMIN COMMAND
# =========================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👑 ADMIN PANEL\n\n"
        "/upload - File upload karein\n"
        "/admin - Admin commands"
    )


# =========================
# MAIN
# =========================

def main():

    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN environment variable missing hai."
        )

    if ADMIN_ID == 0:
        raise ValueError(
            "ADMIN_ID environment variable missing hai."
        )

    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

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
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.PHOTO,
            receive_file
        )
    )

    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.WEB_APP_DATA,
            web_app_data
        )
    )

    print("🤖 Indo Share Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()

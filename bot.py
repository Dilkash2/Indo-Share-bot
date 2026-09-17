import os
import sqlite3
import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
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


# Temporary verification status
verified_users = {}


# =========================
# RENDER WEB SERVER
# =========================

class HealthHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Indo Share Bot is running!")

    def log_message(self, format, *args):
        return


def start_web_server():

    port = int(os.environ.get("PORT", 10000))

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        HealthHandler
    )

    print(f"🌐 Web server running on port {port}")

    server.serve_forever()


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

    # Save current file code for this user
    user_id = update.effective_user.id
    verified_users.pop(user_id, None)

    watch_button = KeyboardButton(
        text="📥 Watch Ad & Unlock",
        web_app=WebAppInfo(
            url=f"{MINI_APP_URL}?file={code}"
        )
    )

    completed_button = KeyboardButton(
        text="✅ I've completed it"
    )

    keyboard = ReplyKeyboardMarkup(
        [
            [watch_button],
            [completed_button]
        ],
        resize_keyboard=True
    )

    await update.message.reply_text(
        "🔒 One quick step\n\n"
        "Watch a short ad to unlock this file,\n"
        "then you'll be brought right back.",
        reply_markup=keyboard
    )


# =========================
# UPLOAD
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
# MINI APP DATA
# =========================

async def web_app_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.message.web_app_data:
        return

    data = update.message.web_app_data.data.strip()

    if not data:
        return

    # Mini App sends:
    # verified|file_code

    if data.startswith("verified|"):

        code = data.split("|", 1)[1].strip()

        if not code:
            return

        file_id = get_file(code)

        if not file_id:
            await update.message.reply_text(
                "❌ File nahi mili ya link invalid hai."
            )
            return

        user_id = update.effective_user.id

        # Mark user as verified
        verified_users[user_id] = code

        await update.message.reply_text(
            "✅ Verification completed!\n\n"
            "Ab neeche **✅ I've completed it** button dabayein."
        )


# =========================
# COMPLETED BUTTON
# =========================

async def completed_button(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    user_id = update.effective_user.id

    code = verified_users.get(user_id)

    if not code:

        await update.message.reply_text(
            "🔒 Pehle **📥 Watch Ad & Unlock** par click karke "
            "verification complete karein."
        )

        return

    file_id = get_file(code)

    if not file_id:

        verified_users.pop(user_id, None)

        await update.message.reply_text(
            "❌ File nahi mili ya link expire ho gaya."
        )

        return

    caption = (
        "⚠️ Is file ko apne Saved Messages mein "
        "forward/save kar lena.\n\n"
        "🗑️ File 90 seconds ke baad automatically delete ho jayegi."
    )

    sent_message = None

    # DOCUMENT
    try:

        sent_message = await context.bot.send_document(
            chat_id=user_id,
            document=file_id,
            caption=caption
        )

    except TelegramError:
        pass

    # VIDEO
    if sent_message is None:

        try:

            sent_message = await context.bot.send_video(
                chat_id=user_id,
                video=file_id,
                caption=caption
            )

        except TelegramError:
            pass

    # AUDIO
    if sent_message is None:

        try:

            sent_message = await context.bot.send_audio(
                chat_id=user_id,
                audio=file_id,
                caption=caption
            )

        except TelegramError:
            pass

    # PHOTO
    if sent_message is None:

        try:

            sent_message = await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=caption
            )

        except TelegramError:
            pass

    if sent_message is None:

        await update.message.reply_text(
            "❌ File send nahi ho paayi.\n\n"
            "Admin se file ko dobara upload karne ko kahen."
        )

        return

    # Remove verification status
    verified_users.pop(user_id, None)

    # Delete file after 90 seconds
    await asyncio.sleep(90)

    try:

        await context.bot.delete_message(
            chat_id=user_id,
            message_id=sent_message.message_id
        )

    except TelegramError:
        pass


# =========================
# ADMIN
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

    # Render web server
    web_thread = threading.Thread(
        target=start_web_server,
        daemon=True
    )

    web_thread.start()

    # Database
    init_db()

    # Telegram bot
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

    # Admin file upload
    app.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.PHOTO,
            receive_file
        )
    )

    # Mini App verification
    app.add_handler(
        MessageHandler(
            filters.StatusUpdate.WEB_APP_DATA,
            web_app_data
        )
    )

    # I've completed it button
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            completed_button
        )
    )

    print("🤖 Indo Share Bot Started...")

    app.run_polling()


if __name__ == "__main__":
    main()

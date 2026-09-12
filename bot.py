import os
import sqlite3
import asyncio

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
    ReplyKeyboardMarkup,
    KeyboardButton,
)

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
            file_id TEXT NOT NULL,
            file_type TEXT DEFAULT 'document'
        )
    """)

    # Agar purani database hai aur file_type column nahi hai
    try:
        cur.execute(
            "ALTER TABLE files ADD COLUMN file_type TEXT DEFAULT 'document'"
        )
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


def save_file(code, file_id, file_type):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        INSERT OR REPLACE INTO files
        (code, file_id, file_type)
        VALUES (?, ?, ?)
        """,
        (code, file_id, file_type)
    )

    conn.commit()
    conn.close()


def get_file(code):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT file_id, file_type
        FROM files
        WHERE code = ?
        """,
        (code,)
    )

    result = cur.fetchone()

    conn.close()

    return result


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    args = context.args

    if not args:

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 Channel se file link open karke file receive karein."
        )

        return

    code = args[0]

    file_data = get_file(code)

    if not file_data:

        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return

    keyboard = [
    [
        KeyboardButton(
            "🚀 Verify & Get File",
            web_app=WebAppInfo(
                url=f"{MINI_APP_URL}?file={code}"
            )
        )
    ]
]

reply_markup=reply_markup
    resize_keyboard=True,
    one_time_keyboard=True
)

    await update.message.reply_text(
        "📁 File Ready!\n\n"
        "Neeche button dabakar verification complete karein.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# UPLOAD COMMAND
# =========================

async def upload_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Sirf admin file upload kar sakta hai."
        )

        return

    await update.message.reply_text(
        "📤 Ab mujhe file bhejo."
    )


# =========================
# RECEIVE FILE
# =========================

async def receive_file(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    telegram_file_id = None
    file_type = None

    if update.message.document:

        telegram_file_id = update.message.document.file_id
        file_type = "document"

    elif update.message.video:

        telegram_file_id = update.message.video.file_id
        file_type = "video"

    elif update.message.audio:

        telegram_file_id = update.message.audio.file_id
        file_type = "audio"

    elif update.message.photo:

        telegram_file_id = update.message.photo[-1].file_id
        file_type = "photo"

    if not telegram_file_id:

        await update.message.reply_text(
            "❌ Ye file type supported nahi hai."
        )

        return

    code = f"file_{update.message.message_id}"

    save_file(
        code,
        telegram_file_id,
        file_type
    )

    bot_username = context.bot.username

    link = f"https://t.me/{bot_username}?start={code}"

    await update.message.reply_text(
        "✅ FILE SAVED SUCCESSFULLY!\n\n"
        f"🔗 File Link:\n{link}\n\n"
        "Is link ko Telegram channel mein post kar sakte ho."
    )


# =========================
# WEB APP VERIFICATION
# =========================

async def web_app_data(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_message:
        return

    message = update.effective_message

    if not message.web_app_data:
        return

    try:
        import json

        data = json.loads(
            message.web_app_data.data
        )

        code = data.get("file")

    except Exception:

        await message.reply_text(
            "❌ Verification data invalid hai."
        )

        return

    if not code:

        await message.reply_text(
            "❌ File code missing hai."
        )

        return

    file_data = get_file(code)

    if not file_data:

        await message.reply_text(
            "❌ File nahi mili."
        )

        return

    file_id, file_type = file_data

    try:

        if file_type == "document":

            sent = await message.reply_document(
                document=file_id,
                caption="📥 Your file\n\n"
                        "⏳ Ye file 90 seconds baad delete ho jayegi."
            )

        elif file_type == "video":

            sent = await message.reply_video(
                video=file_id,
                caption="📥 Your file\n\n"
                        "⏳ Ye file 90 seconds baad delete ho jayegi."
            )

        elif file_type == "audio":

            sent = await message.reply_audio(
                audio=file_id,
                caption="📥 Your file\n\n"
                        "⏳ Ye file 90 seconds baad delete ho jayegi."
            )

        elif file_type == "photo":

            sent = await message.reply_photo(
                photo=file_id,
                caption="📥 Your file\n\n"
                        "⏳ Ye file 90 seconds baad delete ho jayegi."
            )

        else:

            sent = await message.reply_document(
                document=file_id
            )

        # 90 seconds wait
        await asyncio.sleep(90)

        try:
            await sent.delete()
        except Exception:
            pass

    except Exception as e:

        print(
            f"File sending error: {e}"
        )

        await message.reply_text(
            "❌ File send nahi ho saki."
        )


# =========================
# ADMIN
# =========================

async def admin_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👑 ADMIN PANEL\n\n"
        "/upload - File upload\n"
        "/admin - Admin panel"
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
            filters.StatusUpdate.WEB_APP_DATA,
            web_app_data
        )
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

    print(
        "🤖 Indo Share Bot Started..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()

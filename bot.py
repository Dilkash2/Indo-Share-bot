import os
import asyncio
import psycopg2

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MINI_APP_URL = "https://dilkash2.github.io/Indo-Share-bot/"

DATABASE_URL = os.getenv("DATABASE_URL")


# =========================
# DATABASE CONNECTION
# =========================

def get_connection():

    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL environment variable missing hai."
        )

    database_url = DATABASE_URL

    # Kuch services old postgres:// format deti hain
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    return psycopg2.connect(database_url)


# =========================
# CREATE TABLE
# =========================

def init_db():

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            file_id TEXT NOT NULL
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


# =========================
# SAVE FILE
# =========================

def save_file(code, file_id):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute("""
        INSERT INTO files (code, file_id)
        VALUES (%s, %s)
        ON CONFLICT (code)
        DO UPDATE SET file_id = EXCLUDED.file_id
    """, (code, file_id))

    conn.commit()

    cur.close()
    conn.close()


# =========================
# GET FILE
# =========================

def get_file(code):

    conn = get_connection()

    cur = conn.cursor()

    cur.execute(
        "SELECT file_id FROM files WHERE code = %s",
        (code,)
    )

    result = cur.fetchone()

    cur.close()
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

    # Normal /start
    if not args:

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 File lene ke liye channel se file link open karein."
        )

        return

    code = args[0]


    # =========================
    # COMPLETED FILE REQUEST
    # =========================

    if code.startswith("complete_"):

        file_code = code.replace(
            "complete_",
            "",
            1
        )

        file_id = get_file(file_code)

        if not file_id:

            await update.message.reply_text(
                "❌ File nahi mili ya link invalid hai."
            )

            return

        await send_file(
            update.effective_user.id,
            file_id,
            context
        )

        return


    # =========================
    # NORMAL FILE LINK
    # =========================

    file_id = get_file(code)

    if not file_id:

        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return


    # =========================
    # MINI APP BUTTONS
    # =========================

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📥 Watch Ad & Unlock",
                web_app=WebAppInfo(
                    url=f"{MINI_APP_URL}?file={code}"
                )
            )
        ],

        [
            InlineKeyboardButton(
                "✅ I've completed it",
                web_app=WebAppInfo(
                    url=f"{MINI_APP_URL}?file={code}&complete=1"
                )
            )
        ]

    ])


    await update.message.reply_text(

        "🔐 One quick step\n\n"
        "Watch a short ad to unlock this file, "
        "then you'll be brought right back.",

        reply_markup=keyboard
    )


# =========================
# SEND FILE
# =========================

async def send_file(
    user_id,
    file_id,
    context
):

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


    # FAILED

    if sent_message is None:

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ File send nahi ho paayi.\n\n"
                "Admin se file ko dobara upload karne ko kahen."
            )
        )

        return


    # DELETE AFTER 90 SECONDS

    asyncio.create_task(
        delete_file_later(
            context,
            user_id,
            sent_message.message_id
        )
    )


# =========================
# DELETE FILE AFTER 90 SEC
# =========================

async def delete_file_later(
    context,
    user_id,
    message_id
):

    await asyncio.sleep(90)

    try:

        await context.bot.delete_message(
            chat_id=user_id,
            message_id=message_id
        )

    except TelegramError:

        pass


# =========================
# UPLOAD COMMAND
# =========================

async def upload_command(
    update,
    context
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
    update,
    context
):

    if not update.effective_user:
        return


    if update.effective_user.id != ADMIN_ID:
        return


    if not update.message:
        return


    telegram_file_id = None


    if update.message.document:

        telegram_file_id = (
            update.message.document.file_id
        )


    elif update.message.video:

        telegram_file_id = (
            update.message.video.file_id
        )


    elif update.message.audio:

        telegram_file_id = (
            update.message.audio.file_id
        )


    elif update.message.photo:

        telegram_file_id = (
            update.message.photo[-1].file_id
        )


    if not telegram_file_id:

        await update.message.reply_text(
            "❌ Ye file type supported nahi hai."
        )

        return


    # UNIQUE CODE

    code = f"file_{update.message.message_id}"


    # SAVE IN POSTGRESQL

    save_file(
        code,
        telegram_file_id
    )


    bot_username = context.bot.username


    link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?start={code}"
    )


    await update.message.reply_text(

        "✅ FILE SAVED SUCCESSFULLY!\n\n"

        f"🔗 File Link:\n{link}\n\n"

        "Is link ko Telegram channel mein "
        "post kar sakte ho."

    )


# =========================
# ADMIN
# =========================

async def admin_command(
    update,
    context
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


    if not DATABASE_URL:

        raise ValueError(
            "DATABASE_URL environment variable missing hai."
        )


    # CREATE DATABASE TABLE

    init_db()


    # CREATE BOT

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # COMMANDS

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    app.add_handler(
        CommandHandler(
            "upload",
            upload_command
        )
    )


    app.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )


    # FILE RECEIVER

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


# =========================
# START BOT
# =========================

if __name__ == "__main__":

    main()

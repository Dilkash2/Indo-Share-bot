import os
import asyncio
import secrets
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

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    return psycopg2.connect(database_url)


# =========================
# CREATE DATABASE TABLES
# =========================

def init_db():

    conn = get_connection()
    cur = conn.cursor()

    # OLD FILE TABLE
    # Is table ka purana data delete nahi hoga.
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            file_id TEXT NOT NULL
        )
    """)

    # NEW SESSION TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS unlock_sessions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            code TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            message_id BIGINT
        )
    """)

    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_unlock_sessions_user_code
        ON unlock_sessions (user_id, code)
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
# CREATE NEW SESSION
# =========================

def create_session(user_id, code):

    conn = get_connection()
    cur = conn.cursor()

    # Purane sessions ko expire kar do.
    cur.execute("""
        UPDATE unlock_sessions
        SET status = 'expired'
        WHERE user_id = %s
        AND code = %s
        AND status IN ('active', 'verified')
    """, (user_id, code))

    # Short unique token
    token = secrets.token_hex(8)

    cur.execute("""
        INSERT INTO unlock_sessions
        (
            user_id,
            code,
            token,
            status
        )
        VALUES (%s, %s, %s, 'active')
        RETURNING id
    """, (
        user_id,
        code,
        token
    ))

    session_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return token, session_id


# =========================
# SAVE BOT MESSAGE ID
# =========================

def save_session_message_id(session_id, message_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE unlock_sessions
        SET message_id = %s
        WHERE id = %s
    """, (
        message_id,
        session_id
    ))

    conn.commit()

    cur.close()
    conn.close()


# =========================
# COMPLETE SESSION
# =========================

def complete_session(
    user_id,
    code,
    token
):

    conn = get_connection()
    cur = conn.cursor()

    # Sirf ACTIVE session ko SENT banayenge.
    # Agar already sent/expired hai to kuch nahi hoga.
    cur.execute("""
        UPDATE unlock_sessions
        SET
            status = 'sent',
            completed_at = NOW()
        WHERE user_id = %s
        AND code = %s
        AND token = %s
        AND status = 'active'
        RETURNING id
    """, (
        user_id,
        code,
        token
    ))

    result = cur.fetchone()

    conn.commit()

    cur.close()
    conn.close()

    if result:
        return "new"

    # Check karo session already sent hai ya nahi
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT status
        FROM unlock_sessions
        WHERE user_id = %s
        AND code = %s
        AND token = %s
    """, (
        user_id,
        code,
        token
    ))

    result = cur.fetchone()

    cur.close()
    conn.close()

    if result and result[0] == "sent":
        return "already_sent"

    return "invalid"


# =========================
# START
# =========================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.effective_user:
        return

    args = context.args

    # =========================
    # NORMAL /START
    # =========================

    if not args:

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 File lene ke liye channel se file link open karein."
        )

        return

    payload = args[0]


    # ==================================================
    # MINI APP VERIFICATION COMPLETE
    #
    # Format:
    # complete_file_123_TOKEN
    # ==================================================

    if payload.startswith("complete_"):

        complete_data = payload.replace(
            "complete_",
            "",
            1
        )

        # Last "_" ke baad session token hoga.
        # Isse file code ke "_" safe rahenge.
        if "_" not in complete_data:

            await update.message.reply_text(
                "❌ Verification session invalid hai."
            )

            return

        file_code, session_token = complete_data.rsplit(
            "_",
            1
        )

        file_id = get_file(file_code)

        if not file_id:

            await update.message.reply_text(
                "❌ File nahi mili ya link invalid hai."
            )

            return


        # =========================
        # CHECK SESSION
        # =========================

        result = complete_session(
            update.effective_user.id,
            file_code,
            session_token
        )


        # =========================
        # ALREADY COMPLETED
        # =========================

        if result == "already_sent":

            await update.message.reply_text(
                "⚠️ Aapne ye session pehle hi complete kar rakha hai.\n\n"
                "📎 Dobara file lene ke liye pehle "
                "original file link par click karke aayein."
            )

            return


        # =========================
        # INVALID SESSION
        # =========================

        if result == "invalid":

            await update.message.reply_text(
                "❌ Verification session invalid ya expire ho gaya hai.\n\n"
                "📎 Dobara file lene ke liye original file link par click karein."
            )

            return


        # =========================
        # NEW SESSION COMPLETE
        # =========================

        await send_file(
            update.effective_user.id,
            file_id,
            context
        )

        return


    # ==================================================
    # NORMAL FILE LINK
    # ==================================================

    code = payload

    file_id = get_file(code)

    if not file_id:

        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return


    # =========================
    # CREATE NEW SESSION
    # =========================

    session_token, session_id = create_session(
        update.effective_user.id,
        code
    )


    # =========================
    # MINI APP URL
    # =========================

    mini_app_link = (
        f"{MINI_APP_URL}"
        f"?file={code}"
        f"&session={session_token}"
    )


    # =========================
    # BUTTON
    # =========================

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📥 Watch Ad & Unlock",
                web_app=WebAppInfo(
                    url=mini_app_link
                )
            )
        ]

    ])


    # =========================
    # SEND MESSAGE
    # =========================

    sent_message = await update.message.reply_text(

        "🔐 One quick step\n\n"
        "Watch a short ad to unlock this file, "
        "then you'll be brought right back.",

        reply_markup=keyboard
    )


    # =========================
    # SAVE MESSAGE ID
    # =========================

    save_session_message_id(
        session_id,
        sent_message.message_id
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


    # =========================
    # DOCUMENT
    # =========================

    try:

        sent_message = await context.bot.send_document(
            chat_id=user_id,
            document=file_id,
            caption=caption
        )

    except TelegramError:

        pass


    # =========================
    # VIDEO
    # =========================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_video(
                chat_id=user_id,
                video=file_id,
                caption=caption
            )

        except TelegramError:

            pass


    # =========================
    # AUDIO
    # =========================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_audio(
                chat_id=user_id,
                audio=file_id,
                caption=caption
            )

        except TelegramError:

            pass


    # =========================
    # PHOTO
    # =========================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=caption
            )

        except TelegramError:

            pass


    # =========================
    # FAILED
    # =========================

    if sent_message is None:

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ File send nahi ho paayi.\n\n"
                "Admin se file ko dobara upload karne ko kahen."
            )
        )

        return


    # =========================
    # DELETE AFTER 90 SECONDS
    # =========================

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


    # =========================
    # DOCUMENT
    # =========================

    if update.message.document:

        telegram_file_id = (
            update.message.document.file_id
        )


    # =========================
    # VIDEO
    # =========================

    elif update.message.video:

        telegram_file_id = (
            update.message.video.file_id
        )


    # =========================
    # AUDIO
    # =========================

    elif update.message.audio:

        telegram_file_id = (
            update.message.audio.file_id
        )


    # =========================
    # PHOTO
    # =========================

    elif update.message.photo:

        telegram_file_id = (
            update.message.photo[-1].file_id
        )


    # =========================
    # UNSUPPORTED
    # =========================

    if not telegram_file_id:

        await update.message.reply_text(
            "❌ Ye file type supported nahi hai."
        )

        return


    # =========================
    # UNIQUE CODE
    # =========================

    code = f"file_{update.message.message_id}"


    # =========================
    # SAVE IN POSTGRESQL
    # =========================

    save_file(
        code,
        telegram_file_id
    )


    bot_username = context.bot.username


    # =========================
    # CREATE FILE LINK
    # =========================

    link = (
        f"https://t.me/"
        f"{bot_username}"
        f"?start={code}"
    )


    # =========================
    # ADMIN RESPONSE
    # =========================

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

    # =========================
    # CHECK BOT TOKEN
    # =========================

    if not BOT_TOKEN:

        raise ValueError(
            "BOT_TOKEN environment variable missing hai."
        )


    # =========================
    # CHECK ADMIN ID
    # =========================

    if ADMIN_ID == 0:

        raise ValueError(
            "ADMIN_ID environment variable missing hai."
        )


    # =========================
    # CHECK DATABASE
    # =========================

    if not DATABASE_URL:

        raise ValueError(
            "DATABASE_URL environment variable missing hai."
        )


    # =========================
    # CREATE DATABASE TABLES
    # =========================

    init_db()


    # =========================
    # CREATE BOT
    # =========================

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )


    # =========================
    # START COMMAND
    # =========================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )


    # =========================
    # UPLOAD COMMAND
    # =========================

    app.add_handler(
        CommandHandler(
            "upload",
            upload_command
        )
    )


    # =========================
    # ADMIN COMMAND
    # =========================

    app.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )


    # =========================
    # FILE RECEIVER
    # =========================

    app.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.PHOTO,
            receive_file
        )
    )


    # =========================
    # START BOT
    # =========================

    print(
        "🤖 Indo Share Bot Started..."
    )


    app.run_polling()


# =========================
# RUN
# =========================

if __name__ == "__main__":

    main()

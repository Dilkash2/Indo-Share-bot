import os
import asyncio
import json
import uuid
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
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from telegram.error import TelegramError


# ============================================================
# SETTINGS
# ============================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

MINI_APP_URL = "https://dilkash2.github.io/Indo-Share-bot/"

DATABASE_URL = os.getenv("DATABASE_URL")


# ============================================================
# DATABASE CONNECTION
# ============================================================

def get_connection():

    if not DATABASE_URL:
        raise ValueError(
            "DATABASE_URL environment variable missing hai."
        )

    database_url = DATABASE_URL

    # Render/PostgreSQL ke kuch URLs old format mein hote hain
    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    return psycopg2.connect(database_url)


# ============================================================
# CREATE DATABASE TABLES
# ============================================================

def init_db():

    conn = get_connection()
    cur = conn.cursor()

    # --------------------------------------------------------
    # FILES TABLE
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            file_id TEXT NOT NULL
        )
    """)

    # --------------------------------------------------------
    # VERIFICATION SESSIONS TABLE
    # --------------------------------------------------------
    #
    # Har original file-link click par ek NEW session banta hai.
    #
    # session_id:
    #     Unique verification session
    #
    # user_id:
    #     Telegram user
    #
    # file_code:
    #     Kis file ke liye verification ho rahi hai
    #
    # completed:
    #     Verification complete hui ya nahi
    #
    # --------------------------------------------------------

    cur.execute("""
        CREATE TABLE IF NOT EXISTS verification_sessions (
            id SERIAL PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            user_id BIGINT NOT NULL,
            file_code TEXT NOT NULL,
            completed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP NULL
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


# ============================================================
# SAVE FILE
# ============================================================

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


# ============================================================
# GET FILE
# ============================================================

def get_file(code):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT file_id
        FROM files
        WHERE code = %s
        """,
        (code,)
    )

    result = cur.fetchone()

    cur.close()
    conn.close()

    if result:
        return result[0]

    return None


# ============================================================
# CREATE VERIFICATION SESSION
# ============================================================

def create_verification_session(
    user_id,
    file_code
):

    session_id = uuid.uuid4().hex

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO verification_sessions
        (
            session_id,
            user_id,
            file_code,
            completed
        )
        VALUES (%s, %s, %s, FALSE)
    """, (
        session_id,
        user_id,
        file_code
    ))

    conn.commit()

    cur.close()
    conn.close()

    return session_id


# ============================================================
# GET SESSION
# ============================================================

def get_session(session_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            session_id,
            user_id,
            file_code,
            completed
        FROM verification_sessions
        WHERE session_id = %s
    """, (session_id,))

    result = cur.fetchone()

    cur.close()
    conn.close()

    return result


# ============================================================
# COMPLETE SESSION
# ============================================================

def complete_session(
    session_id,
    user_id,
    file_code
):

    conn = get_connection()
    cur = conn.cursor()

    # --------------------------------------------------------
    # Atomic update
    #
    # Agar session pehle hi complete hai,
    # to dobara UPDATE nahi hoga.
    # --------------------------------------------------------

    cur.execute("""
        UPDATE verification_sessions
        SET
            completed = TRUE,
            completed_at = CURRENT_TIMESTAMP
        WHERE
            session_id = %s
            AND user_id = %s
            AND file_code = %s
            AND completed = FALSE
    """, (
        session_id,
        user_id,
        file_code
    ))

    updated_rows = cur.rowcount

    conn.commit()

    cur.close()
    conn.close()

    return updated_rows > 0


# ============================================================
# START COMMAND
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.effective_user:
        return

    args = context.args

    # ========================================================
    # NORMAL /START
    # ========================================================

    if not args:

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 File lene ke liye channel se file link open karein."
        )

        return

    code = args[0]

    # ========================================================
    # OLD COMPLETE LINK SUPPORT
    # ========================================================
    #
    # Purane complete_ links ko completely remove nahi kiya.
    # Lekin ab recommended flow session-based hai.
    #
    # ========================================================

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

    # ========================================================
    # CHECK FILE
    # ========================================================

    file_id = get_file(code)

    if not file_id:

        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return

    # ========================================================
    # CREATE NEW SESSION
    # ========================================================
    #
    # IMPORTANT:
    #
    # Original file link dobara click karne par NEW session
    # milega.
    #
    # Isliye:
    #
    # Same Mini App/session
    #       = same session_id
    #
    # Original file link dobara
    #       = new session_id
    #
    # ========================================================

    session_id = create_verification_session(
        update.effective_user.id,
        code
    )

    # ========================================================
    # MINI APP URL
    # ========================================================

    mini_app_url = (
        f"{MINI_APP_URL}"
        f"?file={code}"
        f"&session={session_id}"
    )

    # ========================================================
    # WATCH AD & UNLOCK BUTTON
    # ========================================================

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📥 Watch Ad & Unlock",
                web_app=WebAppInfo(
                    url=mini_app_url
                )
            )
        ]

    ])

    # ========================================================
    # SEND MESSAGE
    # ========================================================

    await update.message.reply_text(

        "🔐 One quick step\n\n"
        "Watch a short ad to unlock this file, "
        "then you'll be brought right back.",

        reply_markup=keyboard
    )


# ============================================================
# WEB APP DATA
# ============================================================

async def web_app_data_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    if not update.effective_user:
        return

    web_app_data = update.message.web_app_data

    if not web_app_data:
        return

    raw_data = web_app_data.data

    # ========================================================
    # PARSE DATA
    # ========================================================

    try:

        data = json.loads(raw_data)

    except (json.JSONDecodeError, TypeError):

        # ----------------------------------------------------
        # Agar Mini App simple string bheje
        # ----------------------------------------------------

        data = {
            "session_id": raw_data
        }

    # ========================================================
    # DATA
    # ========================================================

    session_id = data.get("session_id")
    file_code = data.get("file_code")
    action = data.get("action")

    # ========================================================
    # VALIDATION
    # ========================================================

    if not session_id:

        await update.message.reply_text(
            "❌ Verification session missing hai."
        )

        return

    # ========================================================
    # SESSION DATABASE SE GET
    # ========================================================

    session = get_session(session_id)

    if not session:

        await update.message.reply_text(
            "❌ Verification Session missing hai.\n\n"
            "नई verification के लिए वापस जाकर file link पर क्लिक करें।"
        )

        return

    (
        saved_session_id,
        saved_user_id,
        saved_file_code,
        completed
    ) = session

    # ========================================================
    # USER CHECK
    # ========================================================

    if saved_user_id != update.effective_user.id:

        await update.message.reply_text(
            "❌ यह verification session इस user के लिए valid नहीं है।"
        )

        return

    # ========================================================
    # FILE CODE CHECK
    # ========================================================

    if file_code and file_code != saved_file_code:

        await update.message.reply_text(
            "❌ Verification session और file match नहीं कर रहे हैं।"
        )

        return

    # ========================================================
    # ONLY VERIFY ACTION
    # ========================================================

    if action and action != "verify":

        await update.message.reply_text(
            "❌ Invalid verification request."
        )

        return

    # ========================================================
    # ALREADY COMPLETED
    # ========================================================

    if completed:

        await update.message.reply_text(
            "⚠️ आपने यह session पहले ही complete कर रखा है।\n\n"
            "नई verification के लिए वापस जाकर file link पर क्लिक करें।"
        )

        return

    # ========================================================
    # COMPLETE SESSION
    # ========================================================

    completed_now = complete_session(
        session_id,
        saved_user_id,
        saved_file_code
    )

    # ========================================================
    # RACE CONDITION / DOUBLE CLICK
    # ========================================================

    if not completed_now:

        await update.message.reply_text(
            "⚠️ आपने यह session पहले ही complete कर रखा है।\n\n"
            "नई verification के लिए वापस जाकर file link पर क्लिक करें।"
        )

        return

    # ========================================================
    # VERIFICATION SUCCESS
    # ========================================================

    keyboard = InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "📥 Get File",
                callback_data=f"getfile:{session_id}"
            )
        ]

    ])

    await update.message.reply_text(

        "✅ Verification successful!\n\n"
        "आपकी verification complete हो गई है।\n"
        "नीचे दिए गए button से अपनी file प्राप्त करें।",

        reply_markup=keyboard
    )


# ============================================================
# GET FILE BUTTON
# ============================================================

async def get_file_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    if not query.from_user:
        return

    # ========================================================
    # CALLBACK DATA
    # ========================================================

    callback_data = query.data or ""

    if not callback_data.startswith("getfile:"):

        return

    session_id = callback_data.replace(
        "getfile:",
        "",
        1
    )

    # ========================================================
    # GET SESSION
    # ========================================================

    session = get_session(session_id)

    if not session:

        await query.message.reply_text(
            "❌ Verification session नहीं मिली।\n\n"
            "नई verification के लिए वापस जाकर file link पर क्लिक करें।"
        )

        return

    (
        saved_session_id,
        saved_user_id,
        file_code,
        completed
    ) = session

    # ========================================================
    # USER CHECK
    # ========================================================

    if saved_user_id != query.from_user.id:

        await query.message.reply_text(
            "❌ यह file button आपके लिए valid नहीं है।"
        )

        return

    # ========================================================
    # COMPLETION CHECK
    # ========================================================

    if not completed:

        await query.message.reply_text(
            "❌ पहले verification complete करें।"
        )

        return

    # ========================================================
    # GET FILE
    # ========================================================

    file_id = get_file(file_code)

    if not file_id:

        await query.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return

    # ========================================================
    # SEND FILE
    # ========================================================

    await query.message.reply_text(
        "📤 File sending..."
    )

    await send_file(
        query.from_user.id,
        file_id,
        context
    )


# ============================================================
# SEND FILE
# ============================================================

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

    # ========================================================
    # DOCUMENT
    # ========================================================

    try:

        sent_message = await context.bot.send_document(
            chat_id=user_id,
            document=file_id,
            caption=caption
        )

    except TelegramError:

        pass

    # ========================================================
    # VIDEO
    # ========================================================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_video(
                chat_id=user_id,
                video=file_id,
                caption=caption
            )

        except TelegramError:

            pass

    # ========================================================
    # AUDIO
    # ========================================================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_audio(
                chat_id=user_id,
                audio=file_id,
                caption=caption
            )

        except TelegramError:

            pass

    # ========================================================
    # PHOTO
    # ========================================================

    if sent_message is None:

        try:

            sent_message = await context.bot.send_photo(
                chat_id=user_id,
                photo=file_id,
                caption=caption
            )

        except TelegramError:

            pass

    # ========================================================
    # FAILED
    # ========================================================

    if sent_message is None:

        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "❌ File send nahi ho paayi.\n\n"
                "Admin se file ko dobara upload karne ko kahen."
            )
        )

        return

    # ========================================================
    # DELETE AFTER 90 SECONDS
    # ========================================================

    asyncio.create_task(
        delete_file_later(
            context,
            user_id,
            sent_message.message_id
        )
    )


# ============================================================
# DELETE FILE AFTER 90 SECONDS
# ============================================================

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


# ============================================================
# UPLOAD COMMAND
# ============================================================

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
        "📤 Ab mujhe file

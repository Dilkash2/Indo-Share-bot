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

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql://",
            1
        )

    return psycopg2.connect(database_url)


# =========================
# CREATE TABLES
# =========================

def init_db():

    conn = get_connection()
    cur = conn.cursor()

    # EXISTING FILES TABLE
    # Is table ko delete/update nahi kiya ja raha
    cur.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            file_id TEXT NOT NULL
        )
    """)

    # USERS TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    conn.commit()

    cur.close()
    conn.close()


# =========================
# SAVE USER
# =========================

def save_user(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO users (user_id)
        VALUES (%s)
        ON CONFLICT (user_id)
        DO UPDATE SET last_seen = NOW()
    """, (user_id,))

    conn.commit()

    cur.close()
    conn.close()


# =========================
# GET ALL USERS
# =========================

def get_all_users():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id
        FROM users
        ORDER BY id ASC
    """)

    users = cur.fetchall()

    cur.close()
    conn.close()

    return [row[0] for row in users]


# =========================
# DELETE BLOCKED USER
# =========================

def delete_user(user_id):

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        "DELETE FROM users WHERE user_id = %s",
        (user_id,)
    )

    conn.commit()

    cur.close()
    conn.close()


# =========================
# USER STATS
# =========================

def get_stats():

    conn = get_connection()
    cur = conn.cursor()

    # TOTAL USERS
    cur.execute("""
        SELECT COUNT(*)
        FROM users
    """)

    total_users = cur.fetchone()[0]

    # THIS MONTH
    cur.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE first_seen >= date_trunc('month', CURRENT_TIMESTAMP)
    """)

    this_month = cur.fetchone()[0]

    # LAST MONTH
    cur.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE first_seen >= date_trunc(
            'month',
            CURRENT_TIMESTAMP - INTERVAL '1 month'
        )
        AND first_seen < date_trunc(
            'month',
            CURRENT_TIMESTAMP
        )
    """)

    last_month = cur.fetchone()[0]

    # ACTIVE TODAY
    cur.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE last_seen >= CURRENT_DATE
    """)

    today = cur.fetchone()[0]

    # ACTIVE THIS WEEK
    cur.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE last_seen >= CURRENT_TIMESTAMP - INTERVAL '7 days'
    """)

    this_week = cur.fetchone()[0]

    cur.close()
    conn.close()

    return (
        total_users,
        this_month,
        last_month,
        today,
        this_week
    )


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

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    # SAVE USER
    if update.effective_user:
        save_user(update.effective_user.id)

    args = context.args

    # NORMAL START
    if not args:

        await update.message.reply_text(
            "👋 Welcome to Indo Share Bot!\n\n"
            "📁 File lene ke liye channel se file link open karein."
        )

        return

    code = args[0]

    # COMPLETED FILE REQUEST
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

    # NORMAL FILE LINK
    file_id = get_file(code)

    if not file_id:

        await update.message.reply_text(
            "❌ File nahi mili ya link invalid hai."
        )

        return

    # MINI APP BUTTON
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "📥 Watch Ad & Unlock",
                web_app=WebAppInfo(
                    url=f"{MINI_APP_URL}?file={code}"
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

    save_user(update.effective_user.id)

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

    code = f"file_{update.message.message_id}"

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
# BROADCAST COMMAND
# =========================

async def broadcast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "❌ Sirf admin broadcast kar sakta hai."
        )

        return

    context.user_data["broadcast_waiting"] = True

    await update.message.reply_text(

        "📢 Broadcast Mode ON\n\n"
        "Ab jo message sabhi users ko bhejna hai, "
        "woh bhejo.\n\n"
        "Text, photo, video ya link bhej sakte ho.\n\n"
        "❌ Cancel karne ke liye /cancel bhejo."

    )


# =========================
# BROADCAST MESSAGE
# =========================

async def broadcast_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        return

    if not context.user_data.get(
        "broadcast_waiting",
        False
    ):
        return

    if not update.message:
        return

    context.user_data["broadcast_waiting"] = False

    users = get_all_users()

    if not users:

        await update.message.reply_text(
            "❌ Abhi database mein koi user nahi hai."
        )

        return

    await update.message.reply_text(
        f"📢 Broadcast start ho gaya.\n\n"
        f"👥 Total users: {len(users)}"
    )

    success = 0
    failed = 0

    for user_id in users:

        try:

            await context.bot.copy_message(
                chat_id=user_id,
                from_chat_id=update.effective_chat.id,
                message_id=update.message.message_id
            )

            success += 1

            await asyncio.sleep(0.05)

        except TelegramError:

            failed += 1

            try:
                delete_user(user_id)
            except Exception:
                pass

    await update.message.reply_text(

        "✅ Broadcast Complete!\n\n"
        f"📨 Sent: {success}\n"
        f"❌ Failed/Blocked: {failed}"

    )


# =========================
# CANCEL BROADCAST
# =========================

async def cancel_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        return

    context.user_data["broadcast_waiting"] = False

    await update.message.reply_text(
        "❌ Broadcast cancel kar diya gaya."
    )


# =========================
# STATS COMMAND
# =========================

async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        return

    (
        total_users,
        this_month,
        last_month,
        today,
        this_week
    ) = get_stats()

    await update.message.reply_text(

        "📊 INDO SHARE STATS\n\n"

        f"👥 Total Users: {total_users}\n\n"

        f"📅 This Month: {this_month}\n"
        f"📅 Last Month: {last_month}\n\n"

        f"🟢 Active Today: {today}\n"
        f"🟢 Active This Week: {this_week}"

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
        "/broadcast - Sabhi users ko message bhejein\n"
        "/stats - Users statistics dekhein\n"
        "/cancel - Broadcast cancel karein\n"
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

    # DATABASE MEIN EXISTING DATA SAFE RAHEGA
    init_db()

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # START
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # UPLOAD
    app.add_handler(
        CommandHandler(
            "upload",
            upload_command
        )
    )

    # BROADCAST
    app.add_handler(
        CommandHandler(
            "broadcast",
            broadcast_command
        )
    )

    # STATS
    app.add_handler(
        CommandHandler(
            "stats",
            stats_command
        )
    )

    # CANCEL
    app.add_handler(
        CommandHandler(
            "cancel",
            cancel_broadcast
        )
    )

    # ADMIN
    app.add_handler(
        CommandHandler(
            "admin",
            admin_command
        )
    )

    # BROADCAST MESSAGE
    app.add_handler(
        MessageHandler(
            filters.ALL & ~filters.COMMAND,
            broadcast_message
        ),
        group=0
    )

    # FILE RECEIVER
    app.add_handler(
        MessageHandler(
            filters.Document.ALL
            | filters.VIDEO
            | filters.AUDIO
            | filters.PHOTO,
            receive_file
        ),
        group=1
    )

    print(
        "🤖 Indo Share Bot Started..."
    )

    app.run_polling()


if __name__ == "__main__":
    main()

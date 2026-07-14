import sqlite3
import os
import uuid
import datetime
import time
import threading
from telethon import TelegramClient, events
from flask import Flask
from threading import Thread

# ---------- ENVIRONMENT VARIABLES ----------
API_ID = int(os.environ.get("API_ID", 12345))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
# -----------------------------------------

# ---------- Flask App for Keep Alive ----------
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is running!"

@app.route('/health')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

# Flask thread start karo
Thread(target=run_flask, daemon=True).start()
# ---------------------------------------------

UPLOAD_DIR = "uploads/"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Database
conn = sqlite3.connect("files.db", check_same_thread=False)
c = conn.cursor()

c.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY,
        file_name TEXT,
        file_path TEXT,
        token TEXT UNIQUE,
        uploader_id INTEGER,
        upload_time TEXT,
        downloads INTEGER DEFAULT 0
    )
""")
conn.commit()

bot = TelegramClient("secure_bot", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ---------- Helper Functions ----------
def generate_token():
    return uuid.uuid4().hex[:16]

def save_file_to_db(file_name, file_path, uploader_id):
    token = generate_token()
    upload_time = datetime.datetime.now().isoformat()
    
    c.execute("""
        INSERT INTO files (file_name, file_path, token, uploader_id, upload_time)
        VALUES (?, ?, ?, ?, ?)
    """, (file_name, file_path, token, uploader_id, upload_time))
    conn.commit()
    return token

def get_file_by_token(token):
    c.execute("""
        SELECT file_path, file_name, downloads 
        FROM files WHERE token = ?
    """, (token,))
    result = c.fetchone()
    
    if not result:
        return None
    
    return {
        "path": result[0],
        "name": result[1],
        "downloads": result[2]
    }

def increment_download(token):
    c.execute("UPDATE files SET downloads = downloads + 1 WHERE token = ?", (token,))
    conn.commit()

def delete_file_from_db(token):
    c.execute("DELETE FROM files WHERE token = ?", (token,))
    conn.commit()

# ---------- Keep Alive Function ----------
def keep_alive():
    """Har 5 minute mein bot ko active rakhne ke liye"""
    while True:
        try:
            print("🔄 Bot is alive...")
            time.sleep(300)  # 5 minute
        except Exception as e:
            print(f"Keep alive error: {e}")
            time.sleep(60)

# Keep alive thread start karo
Thread(target=keep_alive, daemon=True).start()
# -----------------------------------------

# ---------- Bot Commands ----------
@bot.on(events.NewMessage(pattern="/start"))
async def start(event):
    await event.reply(
        "📁 *Permanent File Manager Bot*\n\n"
        "Mujhe koi file bhejo → Main private link doonga\n"
        "Sirf wohi file download hogi, baaki hidden rahengi\n\n"
        "✅ *Features:*\n"
        "• Link PERMANENT hai (kabhi expire nahi hogi)\n"
        "• Unlimited downloads\n"
        "• Sirf file owner delete kar sakta hai\n"
        "• 24/7 Active\n\n"
        "📌 Commands:\n"
        "/myfiles - Apni files dekhein\n"
        "/delete_<token> - File delete karein\n"
        "/ping - Bot alive check",
        parse_mode="markdown"
    )

@bot.on(events.NewMessage(pattern="/ping"))
async def ping(event):
    await event.reply("🏓 Pong! Bot is alive!")

@bot.on(events.NewMessage(func=lambda e: e.document))
async def upload_file(event):
    msg = await event.reply("⏳ File upload ho rahi hai...")
    
    try:
        file_path = await event.message.download_media(file=UPLOAD_DIR)
        file_name = event.message.document.attributes[0].file_name
        
        token = save_file_to_db(file_name, file_path, event.sender_id)
        
        bot_username = (await bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=download_{token}"
        
        await msg.edit(
            f"✅ *File upload ho gayi!*\n\n"
            f"📄 *File:* {file_name}\n"
            f"🔗 *Private Link:*\n{link}\n\n"
            f"📊 *Stats:*\n"
            f"• Link PERMANENT hai (kabhi expire nahi hogi)\n"
            f"• Unlimited downloads\n"
            f"• Sirf aap delete kar sakte ho\n\n"
            f"🗑️ Delete karne ke liye: /delete_{token}",
            parse_mode="markdown",
            link_preview=False
        )
        
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)}")

@bot.on(events.NewMessage(pattern="/start download_(.*)"))
async def download_file(event):
    token = event.pattern_match.group(1)
    file_data = get_file_by_token(token)
    
    if not file_data:
        await event.reply("❌ File nahi mili! Token galat hai ya delete kar di gayi.")
        return
    
    try:
        await event.reply(f"📥 *Download ho raha hai:* {file_data['name']}", parse_mode="markdown")
        await event.reply(file=file_data['path'])
        increment_download(token)
        
    except Exception as e:
        await event.reply(f"❌ Download failed: {str(e)}")

@bot.on(events.NewMessage(pattern="/myfiles"))
async def list_my_files(event):
    c.execute("""
        SELECT file_name, token, downloads, upload_time 
        FROM files WHERE uploader_id = ?
    """, (event.sender_id,))
    
    files = c.fetchall()
    if not files:
        await event.reply("📭 Aapne koi file upload nahi ki hai.")
        return
    
    msg = "📁 *Aapki Files:*\n\n"
    for i, (name, token, downloads, upload_time) in enumerate(files, 1):
        msg += f"{i}. *{name}*\n"
        msg += f"   🔗 Token: `{token}`\n"
        msg += f"   📥 Downloads: {downloads}\n"
        msg += f"   🗑️ /delete_{token}\n\n"
    
    await event.reply(msg, parse_mode="markdown")

@bot.on(events.NewMessage(pattern="/delete_(.*)"))
async def delete_file(event):
    token = event.pattern_match.group(1)
    
    c.execute("SELECT file_path, uploader_id FROM files WHERE token = ?", (token,))
    result = c.fetchone()
    
    if not result:
        await event.reply("❌ File nahi mili!")
        return
    
    file_path, uploader_id = result
    
    if uploader_id != event.sender_id:
        await event.reply("❌ Aap is file ko delete nahi kar sakte! Sirf uploader delete kar sakta hai.")
        return
    
    try:
        os.remove(file_path)
    except:
        pass
    
    delete_file_from_db(token)
    
    await event.reply("✅ File delete kar di gayi! Ab koi download nahi kar sakta.")

@bot.on(events.NewMessage(pattern="/stats"))
async def stats(event):
    c.execute("SELECT COUNT(*) FROM files")
    total_files = c.fetchone()[0]
    
    c.execute("SELECT SUM(downloads) FROM files")
    total_downloads = c.fetchone()[0] or 0
    
    await event.reply(
        f"📊 *Bot Stats:*\n\n"
        f"📁 Total Files: {total_files}\n"
        f"📥 Total Downloads: {total_downloads}\n"
        f"💾 Storage: {UPLOAD_DIR}",
        parse_mode="markdown"
    )

# ---------- MAIN - BOT START ----------
print("🤖 Bot chal raha hai... (24/7 Active)")

try:
    bot.run_until_disconnected()
except Exception as e:
    print(f"❌ Bot crashed: {e}")
    time.sleep(5)
    # Auto-restart
    os.execv(__file__, sys.argv)

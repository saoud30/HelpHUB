# --- START OF FILE helphub1.py (Corrected for Asyncio) ---

import os
import logging
import requests
import json
import tempfile
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Imports for the API server
from fastapi import FastAPI
from pydantic import BaseModel
import uvicorn

from database_manager import db_manager
from dotenv import load_dotenv
load_dotenv()

# Define a data model for our API endpoint
class Notification(BaseModel):
    user_id: int
    message: str

# API Keys and Bot Token
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# We will define the bot application globally so the API can access it
bot_app: Application = None

# Define the FastAPI app and its endpoint
api_app = FastAPI()

@api_app.post("/notify_user")
async def notify_user(notification: Notification):
    """API endpoint to send a message to a user from the dashboard."""
    if not bot_app:
        logger.error("API call received but bot is not initialized.")
        return {"status": "error", "message": "Bot not initialized"}
    try:
        await bot_app.bot.send_message(
            chat_id=notification.user_id,
            text=notification.message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Sent dashboard notification to user {notification.user_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"❌ Failed to send dashboard notification to {notification.user_id}: {e}")
        return {"status": "error", "message": str(e)}

# Bot helper functions (transcription and analysis)
def transcribe_audio_with_groq(audio_data: bytes) -> str:
    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    with tempfile.NamedTemporaryFile(suffix='.ogg', delete=False) as temp_file:
        temp_file.write(audio_data)
        temp_path = temp_file.name
    try:
        with open(temp_path, 'rb') as audio_file:
            files = {'file': ('audio.ogg', audio_file, 'audio/ogg'), 'model': (None, 'whisper-large-v3'), 'response_format': (None, 'json')}
            response = requests.post(url, headers=headers, files=files, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result.get('text', 'Could not transcribe audio')
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return f"❌ Transcription failed: {str(e)}"
    finally:
        try: os.unlink(temp_path)
        except: pass

def analyze_issue_with_llama(text: str) -> dict:
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    prompt = f'Analyze this customer service issue and provide structured JSON:\nIssue: {text}\n{{"summary": "...", "category": "...", "priority": "...", "sentiment": "...", "suggested_resolution": "...", "auto_resolvable": true/false}}'
    data = {"model": "llama3-70b-8192", "messages": [{"role": "user", "content": prompt}], "temperature": 0.3}
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        return json.loads(content[content.find("{"):content.rfind("}")+1])
    except Exception as e:
        logger.error(f"LLM error: {e}")
        return {"summary": text[:100], "category": "General", "priority": "Medium", "sentiment": "Neutral", "suggested_resolution": "Needs human attention", "auto_resolvable": False}

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 **Welcome to HelpHub!**\nSend a voice or text message describing your issue. I’ll create a support ticket, analyze it, and guide you forward.", parse_mode='Markdown')

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, msg = update.effective_user, await update.message.reply_text("🎧 Processing your voice message...")
    try:
        voice_file = await update.message.voice.get_file()
        await msg.edit_text("🎧 Transcribing audio...")
        transcript = transcribe_audio_with_groq(await voice_file.download_as_bytearray())
        if transcript.startswith("❌"):
            await msg.edit_text(transcript); return
        await msg.edit_text("🤖 Analyzing your issue...")
        analysis = analyze_issue_with_llama(transcript)
        ticket_id = db_manager.create_ticket(user.id, user.username or user.first_name, transcript, analysis['summary'], analysis['category'], analysis['priority'], analysis['sentiment'])
        if not ticket_id:
            await msg.edit_text("❌ Failed to create ticket."); return
        response = f"🎫 **Ticket Created: {ticket_id}**\n\n🎧 _{transcript}_\n\n📋 **Summary:** {analysis['summary']}\n• **Category:** {analysis['category']}\n• **Priority:** {analysis['priority']}\n• **Sentiment:** {analysis['sentiment']}\n\n💡 **Resolution:** {analysis['suggested_resolution']}"
        buttons = [[InlineKeyboardButton("✅ Mark as Resolved", callback_data=f"resolve_{ticket_id}")]] if analysis['auto_resolvable'] else []
        buttons.append([InlineKeyboardButton("👨‍💼 Forward to Human", callback_data=f"forward_{ticket_id}"), InlineKeyboardButton("ℹ️ Ticket Status", callback_data=f"status_{ticket_id}")])
        await msg.edit_text(response, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Voice error: {e}"); await msg.edit_text(f"❌ Error: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, user_text, msg = update.effective_user, update.message.text, await update.message.reply_text("🤖 Analyzing your issue...")
    try:
        analysis = analyze_issue_with_llama(user_text)
        ticket_id = db_manager.create_ticket(user.id, user.username or user.first_name, user_text, analysis['summary'], analysis['category'], analysis['priority'], analysis['sentiment'])
        if not ticket_id:
            await msg.edit_text("❌ Failed to create ticket."); return
        response = f"🎫 **Ticket Created: {ticket_id}**\n\n💬 _{user_text}_\n\n📋 **Summary:** {analysis['summary']}\n• **Category:** {analysis['category']}\n• **Priority:** {analysis['priority']}\n• **Sentiment:** {analysis['sentiment']}\n\n💡 **Resolution:** {analysis['suggested_resolution']}"
        buttons = [[InlineKeyboardButton("✅ Mark as Resolved", callback_data=f"resolve_{ticket_id}")]] if analysis['auto_resolvable'] else []
        buttons.append([InlineKeyboardButton("👨‍💼 Forward to Human", callback_data=f"forward_{ticket_id}"), InlineKeyboardButton("ℹ️ Ticket Status", callback_data=f"status_{ticket_id}")])
        await msg.edit_text(response, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Text error: {e}"); await msg.edit_text(f"❌ Error: {str(e)}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, ticket_id = query.data.split('_', 1)
    ticket = db_manager.get_ticket(ticket_id)
    if not ticket: await query.edit_message_text("❌ Ticket not found."); return
    if action == "resolve":
        db_manager.update_ticket_status(ticket_id, "resolved", "Auto-resolved by customer")
        await query.edit_message_text(f"✅ Ticket {ticket_id} marked as resolved.", parse_mode='Markdown')
    elif action == "forward":
        db_manager.update_ticket_status(ticket_id, "forwarded")
        await query.edit_message_text(f"🔄 Ticket {ticket_id} forwarded to human support.", parse_mode='Markdown')
    elif action == "status":
        await query.edit_message_text(f"📋 **Ticket Status: {ticket_id}**\n\n• **Status:** {ticket['status'].title()}\n• **Category:** {ticket['category']}\n• **Priority:** {ticket['priority']}\n• **Created:** {ticket['created_at'][:19]}\n• **Summary:** {ticket['summary']}", parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("**HelpHub Commands:**\n/start - Start bot\n/help - Show help\n/mystatus - Your recent tickets", parse_mode='Markdown')

async def my_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, tickets = update.effective_user, db_manager.get_user_tickets(user.id)
    if not tickets: await update.message.reply_text("📋 You don't have any tickets yet."); return
    msg = "📋 **Your Recent Tickets:**\n\n"
    status_icons = {"open": "🟡", "resolved": "✅", "forwarded": "🔄"}
    for t in tickets[:5]:
        icon = status_icons.get(t['status'], "❓")
        summary = t['summary'][:50] + "..." if len(t['summary']) > 50 else t['summary']
        msg += f"{icon} **{t['id']}** ({t['status'].title()})\n_{summary}_\n\n"
    await update.message.reply_text(msg, parse_mode='Markdown')


# --- MODIFIED AND CORRECTED main() and helper ---

async def run_bot():
    """Starts and runs the bot until interrupted."""
    # The 'async with' block handles graceful startup and shutdown
    async with bot_app:
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot has started polling...")
        
        # Keep the bot running until we receive a signal to stop
        # This creates a 'Future' that will never complete on its own
        await asyncio.Future()
        
        await bot_app.updater.stop()
        await bot_app.stop()
        logger.info("Bot has stopped.")

async def main():
    """Sets up and runs the Bot and API server concurrently."""
    global bot_app
    
    # Set up the Telegram bot application
    bot_app = Application.builder().token(TELEGRAM_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("help", help_command))
    bot_app.add_handler(CommandHandler("mystatus", my_status))
    bot_app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    bot_app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Set up the Uvicorn server configuration for our API
    api_config = uvicorn.Config(api_app, host="127.0.0.1", port=8000, log_level="info")
    api_server = uvicorn.Server(api_config)
    
    # Run the bot and the API server concurrently
    logger.info("🚀 Starting HelpHub Bot and API Server...")
    try:
        await asyncio.gather(
            run_bot(),
            api_server.serve(),
        )
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Shutting down application...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "Cannot run the event loop while another loop is running" in str(e):
             logger.warning("Ignoring nested event loop error during shutdown.")
        else:
            raise
    except Exception as e:
        logger.error(f"❌ Application failed to start: {e}")
# --- END OF FILE helphub1.py ---
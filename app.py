import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from config import TELEGRAM_BOT_TOKEN
from rag_pipeline import rag_query

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi! Ask me anything based on the PDFs I've read.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a question, and I'll try to answer using the documents.")

async def bot_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    answer = rag_query(question)
    await update.message.reply_text(answer)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_reply))
    app.run_polling()

if __name__ == "__main__":
    main()

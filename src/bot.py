import os
import asyncio
from zlibrary import AsyncZlib
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! Send me a message with your search query, and I will find books for you."
    )

async def search_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip().lower()

    if update.message.chat.type in ["group", "supergroup"]:
        bot_username = (await context.bot.get_me()).username.lower()
        if f"@{bot_username}" not in query:
            return  # Ignore messages in groups unless the bot is mentioned

        query = query.replace(f"@{bot_username}", "").strip()
    paginator = await context.application.zlib.search(q=query, count=5)
    await paginator.next()

    if paginator.result:
        reply = ""
        for i, book_item in enumerate(paginator.result, start=1):
            book = await book_item.fetch()
            reply += f"{i}. Title: {book.get('name')}\n"
            
            authors = book.get("authors", [])
            if authors:
                author_names = ", ".join([author["author"] for author in authors])
                reply += f"Authors: {author_names}\n"

            reply += f"Format: {book.get('extension', 'Unknown')}\n"
            reply += f"Download: {book.get('download_url', 'Unavailable')}\n\n"
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("No results found.")

async def zlib_login():
    """Handle the asynchronous login for zlibrary."""
    zlibrary_email = os.environ.get("ZLOGIN")
    zlibrary_password = os.environ.get("ZPASSW")

    if not zlibrary_email or not zlibrary_password:
        print("Please set the environment variables ZLOGIN and ZPASSW.")
        return None

    zlib = AsyncZlib()
    await zlib.login(zlibrary_email, zlibrary_password)
    return zlib

def main():
    """Initializes the bot and runs it."""
    telegram_token = os.environ.get("TELEGRAM_TOKEN")

    if not telegram_token:
        print("Please set the environment variable TELEGRAM_TOKEN.")
        return

    # Create the Telegram bot application
    application = ApplicationBuilder().token(telegram_token).build()

    # Perform the zlibrary login asynchronously
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    zlib = loop.run_until_complete(zlib_login())

    if not zlib:
        return

    # Store zlib instance in application
    application.zlib = zlib

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (filters.ChatType.GROUP | filters.ChatType.SUPERGROUP), search_books))

    # Run the bot
    print("Bot is running...")
    application.run_polling()

if __name__ == "__main__":
    main()
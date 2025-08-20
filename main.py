# main.py
import asyncio
import threading
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from rag.document_loader import load_documents_from_folder
from rag.rag_engine import query_rag
from auth.ad_auth import authenticate_user
from auth.session import create_session, get_session, increment_login_attempts, is_user_locked
from dotenv import load_dotenv
import os
import json
import re

load_dotenv()

# === Настройки ===
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", 8000))

# === Состояния ===
LOGIN, PASSWORD = range(2)

# === FastAPI ===
fastapi_app = FastAPI()


class QueryRequest(BaseModel):
    question: str


@fastapi_app.post("/query")
def api_query(request: QueryRequest):
    result = query_rag(request.question)
    return result


def run_fastapi():
    uvicorn.run(fastapi_app, host=API_HOST, port=API_PORT)


# === Telegram Bot ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔐 Войти", callback_data="login")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Добро пожаловать в корпоративного помощника!", reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "login":
        await query.edit_message_text("Введите логин:")
        context.user_data["awaiting"] = "login"
    elif query.data == "help":
        await query.edit_message_text(
            "Я помогу найти ответы по инструкциям.\n"
            "Сначала войдите, затем задавайте вопросы."
        )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if is_user_locked(user_id):
        await update.message.reply_text("❌ Заблокировано на 20 минут.")
        return

    # Обработка авторизации
    if context.user_data.get("awaiting") == "login":
        username = text
        if not username:
            await update.message.reply_text("Логин не может быть пустым. Введите логин:")
            return
        
        context.user_data["username"] = username
        await update.message.reply_text("Введите пароль:")
        context.user_data["awaiting"] = "password"
        return

    if context.user_data.get("awaiting") == "password":
        username = context.user_data["username"]
        password = text
        if not password:
            await update.message.reply_text("Пароль не может быть пустым. Введите пароль:")
            return
            
        success, full_name = authenticate_user(username, password)

        if success:
            session_id = create_session(user_id, username, full_name)
            context.user_data["session_id"] = session_id
            context.user_data["awaiting"] = None
            await update.message.reply_text(f"✅ Добро пожаловать, {full_name}!")
        else:
            attempts = increment_login_attempts(user_id)
            if attempts >= 3:
                await update.message.reply_text(
                    "❌ Доступ заблокирован на 20 минут."
                )
            else:
                remaining = 3 - attempts
                await update.message.reply_text(
                    f"❌ Ошибка аутентификации. Осталось попыток: {remaining}"
                )
        return

    # Обычный вопрос
    session_id = context.user_data.get("session_id")
    if not session_id or not get_session(session_id):
        keyboard = [[InlineKeyboardButton("🔐 Войти", callback_data="login")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Ваша сессия истекла. Пожалуйста, войдите снова.", reply_markup=reply_markup
        )
        return

    # Обработка запроса
    try:
        result = query_rag(text)
        
        answer = result.get("answer", "Извините, ответ не найден.")
        source = result.get("source")
        images = result.get("images", [])
        link_to_document = result.get("link_to_document")

        # Формируем текст ответа
        response_text = f"🔍 {answer}"
        
        if source:
            response_text += f"\n\n📌 Источник: {source}"
            
        if link_to_document:
            response_text += f"\n\n📎 Подробнее: {link_to_document}"

        await update.message.reply_text(response_text)

        # Отправляем скриншоты
        if images:
            await update.message.reply_text("📷 Вот скриншоты из инструкции:")
            for img in images:
                img_path = img.get("img_path")
                caption = img.get("caption", "Скриншот")

                if img_path and os.path.exists(img_path):
                    try:
                        with open(img_path, "rb") as photo:
                            await context.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=photo,
                                caption=caption
                            )
                    except Exception as e:
                        await update.message.reply_text(f"📷 Не удалось отправить: {caption}")
                else:
                    await update.message.reply_text(f"📷 {caption} (файл не найден)")
                    
    except Exception as e:
        await update.message.reply_text(f"Ошибка при обработке запроса: {str(e)}")


def run_telegram():
    if not BOT_TOKEN:
        print("❗ Установите TELEGRAM_BOT_TOKEN в .env")
        return
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("✅ Telegram-бот запущен. Ожидание сообщений...")
    app.run_polling()


# === Watcher ===
class WatcherHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory or not event.src_path.lower().endswith((".pdf", ".docx")):
            return
        print(f"🔄 Изменён: {event.src_path}")
        load_documents_from_folder()

    def on_created(self, event):
        if event.is_directory or not event.src_path.lower().endswith((".pdf", ".docx")):
            return
        print(f"🆕 Добавлен: {event.src_path}")
        load_documents_from_folder()


def run_watcher():
    load_documents_from_folder()
    event_handler = WatcherHandler()
    observer = Observer()
    observer.schedule(event_handler, "documents", recursive=False)
    observer.start()
    try:
        while True:
            asyncio.run(asyncio.sleep(1))
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# === Запуск всех сервисов ===
if __name__ == "__main__":
    threading.Thread(target=run_fastapi, daemon=True).start()
    threading.Thread(target=run_watcher, daemon=True).start()
    run_telegram()
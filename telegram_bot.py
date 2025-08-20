# telegram_bot.py (обновлённый с AD)
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from auth.ad_auth import authenticate_user
from auth.session import create_session, get_session, increment_login_attempts, is_user_locked
from dotenv import load_dotenv
import requests
import os

load_dotenv()

# Состояния
LOGIN, PASSWORD = range(2)

# Настройки
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = os.getenv("API_URL", "http://localhost:8000/query")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if is_user_locked(user_id):
        await update.message.reply_text(
            "❌ Вы временно заблокированы из-за множества неудачных попыток входа.\n"
            "Повторите попытку через 20 минут."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "🔐 Привет! Требуется авторизация.\n"
        "Введите ваш логин (например, ivanov):"
    )
    return LOGIN


async def ask_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip()
    if not username:
        await update.message.reply_text("Логин не может быть пустым. Введите логин:")
        return LOGIN

    context.user_data['username'] = username
    await update.message.reply_text("Введите пароль:")
    return PASSWORD


async def ask_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = context.user_data.get('username')
    password = update.message.text

    if is_user_locked(user_id):
        await update.message.reply_text("❌ Вы заблокированы на 20 минут.")
        return ConversationHandler.END

    success, message = authenticate_user(username, password)

    if success:
        session_id = create_session(user_id, username, message)
        context.user_data['session_id'] = session_id
        await update.message.reply_text(
            f"✅ Вход выполнен! Добро пожаловать, {message}!\n"
            "Теперь вы можете задавать вопросы по документации."
        )
        return ConversationHandler.END
    else:
        attempts = increment_login_attempts(user_id)
        remaining = MAX_LOGIN_ATTEMPTS - attempts

        if remaining > 0:
            await update.message.reply_text(
                f"❌ {message}\n"
                f"Осталось попыток: {remaining}\n"
                "Введите пароль:"
            )
            return PASSWORD
        else:
            await update.message.reply_text(
                "🚫 Достигнуто максимальное количество попыток.\n"
                "Доступ заблокирован на 20 минут."
            )
            return ConversationHandler.END


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get('session_id')
    if not session_id or not get_session(session_id):
        await update.message.reply_text("Сессия устарела. Используйте /start для входа.")
        return

    user_text = update.message.text.strip()
    if not user_text:
        await update.message.reply_text("Введите корректный вопрос.")
        return

    try:
        response = requests.post(API_URL, json={"question": user_text}, timeout=30)
        if response.status_code != 200:
            await update.message.reply_text("Ошибка при поиске ответа.")
            return

        data = response.json()
        answer = data.get("answer", "Ответ не найден.")
        await update.message.reply_text(f"🔍 {answer}")

        images = data.get("images", [])
        if images:
            await update.message.reply_text("📎 Вот скриншоты из документа:")

            for img in images:
                img_path = img.get("img_path")
                caption = img.get("caption", "Скриншот")

                if os.path.exists(img_path):
                    with open(img_path, 'rb') as photo:
                        try:
                            await context.bot.send_photo(
                                chat_id=update.effective_chat.id,
                                photo=photo,
                                caption=f"🖼️ {caption}"
                            )
                        except Exception as e:
                            await update.message.reply_text(f"📷 {caption} (не удалось отправить)")
                else:
                    await update.message.reply_text(f"📷 {caption}")

    except requests.exceptions.Timeout:
        await update.message.reply_text("⏳ Запрос слишком долгий. Уточните вопрос.")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {str(e)}")


def main():
    if not BOT_TOKEN:
        print("❗ Установите TELEGRAM_BOT_TOKEN в .env")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_login)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, ask_password)],
        },
        fallbacks=[CommandHandler("start", start)]
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("✅ Telegram-бот запущен. Ожидание команд...")
    app.run_polling()


if __name__ == "__main__":
    main()
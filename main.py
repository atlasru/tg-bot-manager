import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.enums import ParseMode
from openai import AsyncOpenAI
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

# Настройки
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
B_AI_API_KEY = os.getenv("B_AI_API_KEY")
B_AI_BASE_URL = os.getenv("B_AI_BASE_URL", "https://api.b.ai/v1")
B_AI_MODEL = os.getenv("B_AI_MODEL", "deepseek-v4-flash")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Настраиваем логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создаём бота и диспетчер
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Клиент для работы с b.ai API (совместим с OpenAI)
client = AsyncOpenAI(
    api_key=B_AI_API_KEY,
    base_url=B_AI_BASE_URL
)

# Системный промпт - здесь мы задаём "личность" бота
SYSTEM_PROMPT = """Ты — дружелюбный и профессиональный помощник. Отвечай на русском языке, тепло и заботливо, но без лишних слов. Используй умеренно эмодзи. Если не знаешь ответа на вопрос, честно скажи, что уточнишь у человека, и предложи оставить сообщение. Никогда не давай точных сроков или цен, если не уверен — всегда предлагай связаться с менеджером."""

# Хранилище истории сообщений для каждого пользователя
user_histories = {}

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    await message.answer(
        "Привет! 👋 Я — виртуальный помощник. Напиши мне свой вопрос, и я постараюсь помочь!"
    )

@dp.message()
async def handle_message(message: types.Message):
    """Обработчик всех текстовых сообщений"""
    user_id = message.from_user.id
    user_text = message.text
    
    # Получаем или создаём историю для этого пользователя
    if user_id not in user_histories:
        user_histories[user_id] = []
    
    # Добавляем сообщение пользователя в историю
    user_histories[user_id].append({"role": "user", "content": user_text})
    
    # Ограничиваем историю последними 10 сообщениями, чтобы не превышать лимиты
    if len(user_histories[user_id]) > 10:
        user_histories[user_id] = user_histories[user_id][-10:]
    
    try:
        # Отправляем запрос в b.ai API
        messages = [{"role": "system", "content": SYSTEM_PROMPT}] + user_histories[user_id]
        
        response = await client.chat.completions.create(
            model=B_AI_MODEL,
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        # Получаем ответ от модели
        assistant_message = response.choices[0].message.content
        
        # Добавляем ответ в историю
        user_histories[user_id].append({"role": "assistant", "content": assistant_message})
        
        # Отправляем ответ пользователю
        await message.answer(assistant_message)
        
    except Exception as e:
        logger.error(f"Ошибка при обращении к API: {e}")
        await message.answer(
            "Извини, произошла техническая заминка. Я передам твой вопрос человеку, и он скоро ответит! 🙏"
        )

# FastAPI приложение для webhook
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Действия при запуске и остановке приложения"""
    # При запуске устанавливаем webhook
    webhook_info = await bot.get_webhook_info()
    if webhook_info.url != WEBHOOK_URL:
        await bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    yield
    # При остановке удаляем webhook
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)

@app.post("/webhook")
async def telegram_webhook(request: Request):
    """Эндпоинт для получения обновлений от Telegram"""
    try:
        data = await request.json()
        update = types.Update(**data)
        await dp.feed_update(bot=bot, update=update)
        return {"ok": True}
    except Exception as e:
        logger.error(f"Ошибка обработки webhook: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/")
async def root():
    """Простая проверка, что сервер работает"""
    return {"status": "Bot is running"}
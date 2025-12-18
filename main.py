import os
import asyncio
import logging
import json
from datetime import datetime
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp

# --- تنظیمات اختصاصی ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
# این آیدی رو بعد از ساخت سرویس در Render، جایگزین کنید (مثلا: https://mybot.onrender.com)
BASE_URL = "https://YOUR_APP_NAME.onrender.com" 

# --- پیکربندی سرور و ربات ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
app = FastAPI()
scheduler = AsyncIOScheduler()
DB_ALERTS = "alerts.json"

class BotStates(StatesGroup):
    waiting_for_convert = State()
    waiting_for_alert_value = State()

# --- مدیریت داده‌های محلی ---
def load_alerts():
    if not os.path.exists(DB_ALERTS): return {}
    try:
        with open(DB_ALERTS, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_alerts(data):
    with open(DB_ALERTS, 'w', encoding='utf-8') as f: json.dump(data, f)

async def get_prices():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {item['title']: item['price']['sell'] * 1000 for item in data['prices']}
    except: return None

# --- هندلرهای ربات (قیمت، تبدیل، حباب، هشدار) ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="💰 قیمت‌های لحظه‌ای"), types.KeyboardButton(text="🔄 تبدیل‌گر واحد"))
    kb.row(types.KeyboardButton(text="🔔 ثبت هشدار قیمت"), types.KeyboardButton(text="📊 محاسبه حباب سکه"))
    await message.answer("💎 خوش آمدید! این ربات روی وب‌سرویس فعال است.", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text == "💰 قیمت‌های لحظه‌ای")
async def show_prices(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا در دریافت قیمت.")
    text = f"🕒 بروزرسانی: {datetime.now().strftime('%H:%M')}\n\n"
    for k, v in list(prices.items())[:6]:
        text += f"🔹 {k}: {v:,} ریال\n"
    await message.answer(text, parse_mode="Markdown")

# (بقیه هندلرهای تبدیل‌گر و حباب که در نسخه قبلی بود اینجا قرار می‌گیرند...)

# --- تنظیمات Webhook و FastAPI ---
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

@app.get("/")
async def index():
    return {"status": "bot is running"}

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH)
    # زمان‌بندی‌ها
    scheduler.add_job(auto_report, 'cron', hour=12, minute=0)
    scheduler.add_job(auto_report, 'cron', hour=0, minute=0)
    scheduler.start()

async def auto_report():
    prices = await get_prices()
    if prices:
        text = "📢 گزارش خودکار قیمت‌ها در گروه"
        await bot.send_message(GROUP_ID, text)

# دستور اجرا برای Render: uvicorn main:app --host 0.0.0.0 --port 10000

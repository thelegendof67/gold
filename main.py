import logging
from datetime import datetime
import pytz
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp

# --- تنظیمات اختصاصی ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'
BASE_URL = "https://gold-w3ch.onrender.com" 
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TEHRAN_TZ)

async def get_prices():
    """دریافت قیمت‌ها از منبع"""
    headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/132.0.0.0'}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {item['title']: int(item['price']['sell'] * 1000) for item in data['prices']}
    except Exception as e:
        logging.error(f"Error fetching prices: {e}")
    return None

async def send_hourly_report():
    """ارسال گزارش رأس ساعت"""
    prices = await get_prices()
    if not prices: return

    now_str = datetime.now(TEHRAN_TZ).strftime('%H:%M')
    text = f"🕒 **گزارش بازار طلا و سکه (ساعت {now_str})**\n\n"
    
    important_items = ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه", "ربع سکه", "مثقال طلا"]
    
    for item_name in important_items:
        for key, val in prices.items():
            if item_name in key:
                text += f"🔹 {key}: `{val:,}` ریال\n"
                break
    
    try:
        await bot.send_message(GROUP_ID, text, parse_mode="Markdown")
        logging.info(f"Report sent successfully at {now_str}")
    except Exception as e:
        logging.error(f"Failed to send hourly message: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # تنظیم وب‌هوک برای بیدار ماندن سرور
    await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH, drop_pending_updates=True)
    
    if not scheduler.running:
        # تنظیم برای اجرا دقیقاً رأس هر ساعت (minute=0)
        scheduler.add_job(send_hourly_report, 'cron', minute=0)
        scheduler.start()
        logging.info("Scheduler started: Every hour at minute 00.")
        
    yield
    await bot.delete_webhook()
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health():
    return {"status": "active", "task": "hourly_report_at_00_minutes"}

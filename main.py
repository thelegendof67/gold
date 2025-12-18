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

# --- تنظیمات اختصاصی هماهنگ با لینک شما ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'
BASE_URL = "https://gold-w3ch.onrender.com" 
WEBHOOK_PATH = f"/bot/{API_TOKEN}"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()
app = FastAPI()
scheduler = AsyncIOScheduler()
DB_ALERTS = "alerts.json"

class BotStates(StatesGroup):
    waiting_for_convert = State()
    waiting_for_alert_value = State()

# --- توابع کمکی مدیریت داده ---
def load_alerts():
    if not os.path.exists(DB_ALERTS): return {}
    try:
        with open(DB_ALERTS, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_alerts(data):
    with open(DB_ALERTS, 'w', encoding='utf-8') as f: 
        json.dump(data, f, ensure_ascii=False, indent=4)

async def get_prices():
    headers = {'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Edge/132.0.0.0'}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL, headers=headers, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {item['title']: item['price']['sell'] * 1000 for item in data['prices']}
    except Exception as e:
        logging.error(f"Error fetching: {e}")
    return None

# --- هندلرهای پیام ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="💰 قیمت‌های لحظه‌ای"), types.KeyboardButton(text="🔄 تبدیل‌گر واحد"))
    kb.row(types.KeyboardButton(text="🔔 ثبت هشدار قیمت"), types.KeyboardButton(text="📊 محاسبه حباب سکه"))
    await message.answer("💎 **به دستیار هوشمند بازار طلا خوش آمدید**\n\nاین ربات روی وب‌سرویس فعال است و قیمت‌ها را گزارش می‌دهد.", reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text == "💰 قیمت‌های لحظه‌ای")
async def show_prices(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا در اتصال به بازار.")
    text = f"🕒 **بروزرسانی:** {datetime.now().strftime('%H:%M:%S')}\n\n"
    for title, val in list(prices.items())[:7]:
        text += f"🔹 {title}: `{val:,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔄 تبدیل‌گر واحد")
async def converter_init(message: types.Message, state: FSMContext):
    await message.answer("💸 مبلغ مورد نظر خود را به **تومان** وارد کنید:")
    await state.set_state(BotStates.waiting_for_convert)

@dp.message(BotStates.waiting_for_convert)
async def converter_proc(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ فقط عدد انگلیسی وارد کنید.")
    amount = int(message.text)
    prices = await get_prices()
    g18 = (prices.get("گرم طلا عیار ۱۸", 0)/10) or 1
    coin = (prices.get("سکه تمام", 0)/10) or 1
    
    text = f"⚖️ **با {amount:,} تومان می‌توانید بخرید:**\n\n"
    text += f"🔸 طلا ۱۸ عیار: `{round(amount/g18, 3)}` گرم\n"
    text += f"🔸 سکه تمام: `{round(amount/coin, 2)}` عدد\n"
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

@dp.message(F.text == "📊 محاسبه حباب سکه")
async def bubble_calc(message: types.Message):
    prices = await get_prices()
    text = "🧼 **حباب تقریبی سکه در بازار:**\n\n"
    for s in ["سکه تمام", "نیم سکه", "ربع سکه"]:
        p = prices.get(s, 0)
        text += f"🔸 {s}: `{int(p * 0.14):,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔔 ثبت هشدار قیمت")
async def alert_menu(message: types.Message):
    builder = InlineKeyboardBuilder()
    for item in ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه", "ربع سکه"]:
        builder.row(types.InlineKeyboardButton(text=item, callback_data=f"set:{item}"))
    await message.answer("🎯 آیتم مورد نظر برای هشدار را انتخاب کنید:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set:"))
async def alert_step2(callback: types.CallbackQuery, state: FSMContext):
    item = callback.data.split(":")[1]
    await state.update_data(item=item)
    await callback.message.edit_text(f"📉 قیمت هدف برای **{item}** را به **ریال** وارد کنید:")
    await state.set_state(BotStates.waiting_for_alert_value)

@dp.message(BotStates.waiting_for_alert_value)
async def alert_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ نامعتبر.")
    data = await state.get_data()
    item, price = data['item'], int(message.text)
    alerts = load_alerts()
    user_id = str(message.from_user.id)
    if user_id not in alerts: alerts[user_id] = {}
    alerts[user_id][item] = price
    save_alerts(alerts)
    await message.answer(f"✅ ثبت شد. اگر {item} به کمتر از {price:,} ریال رسید خبرتان می‌دهم.")
    await state.clear()

# --- وظایف خودکار و Webhook ---
@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)

@app.get("/")
async def health(): return {"status": "ok"}

async def check_alerts_task():
    prices = await get_prices()
    if not prices: return
    alerts = load_alerts()
    for uid, u_alerts in list(alerts.items()):
        for item, target in list(u_alerts.items()):
            if item in prices and prices[item] <= target:
                try:
                    await bot.send_message(uid, f"🚨 **وقت خرید!**\n{item} به {prices[item]:,} ریال رسید!")
                    del alerts[uid][item]
                except: pass
    save_alerts(alerts)

async def auto_report():
    prices = await get_prices()
    if prices:
        text = "📢 **گزارش ۱۲ ساعته بازار**\n\n"
        for k, v in list(prices.items())[:5]: text += f"▪️ {k}: {v:,}\n"
        try: await bot.send_message(GROUP_ID, text)
        except: pass

@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH)
    scheduler.add_job(check_alerts_task, 'interval', minutes=5)
    scheduler.add_job(auto_report, 'cron', hour=12, minute=0)
    scheduler.add_job(auto_report, 'cron', hour=0, minute=0)
    scheduler.start()

import os
import asyncio
import logging
import json
from datetime import datetime
import pytz # برای تنظیم دقیق زمان ایران
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import Update
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import aiohttp

# --- پیکربندی ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'
BASE_URL = "https://gold-w3ch.onrender.com" 
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
TIMEZONE = pytz.timezone('Asia/Tehran')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
DB_ALERTS = "alerts.json"

class BotStates(StatesGroup):
    waiting_for_convert = State()
    waiting_for_alert_value = State()

# --- توابع مدیریت داده ---
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
                    # استخراج قیمت‌ها و تبدیل به ریال (ضرب در 1000 طبق ساختار API)
                    return {item['title']: int(item['price']['sell'] * 1000) for item in data['prices']}
    except Exception as e:
        logging.error(f"Error in fetching prices: {e}")
    return None

# --- هندلرهای اصلاح شده ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="💰 قیمت‌های لحظه‌ای"), types.KeyboardButton(text="🔄 تبدیل‌گر واحد"))
    kb.row(types.KeyboardButton(text="🔔 ثبت هشدار قیمت"), types.KeyboardButton(text="📊 محاسبه حباب سکه"))
    await message.answer("💎 **به دستیار هوشمند بازار طلا خوش آمدید**\nوضعیت زمان‌بندی: فعال ✅", reply_markup=kb.as_markup(resize_keyboard=True))

# اصلاح بخش تبدیل‌گر (دیباگ شده)
@dp.message(F.text == "🔄 تبدیل‌گر واحد")
async def converter_init(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_convert)
    await message.answer("💸 مبلغ مورد نظر خود را به **تومان** وارد کنید:\n(مثلاً: 10000000)")

@dp.message(BotStates.waiting_for_convert)
async def converter_proc(message: types.Message, state: FSMContext):
    input_text = message.text.strip()
    if not input_text.isdigit():
        return await message.answer("⚠️ لطفاً فقط عدد انگلیسی وارد کنید.")
    
    toman_amount = int(input_text)
    rial_amount = toman_amount * 10 # تبدیل تومان به ریال برای محاسبات
    prices = await get_prices()
    
    if not prices:
        return await message.answer("❌ خطا در دریافت قیمت‌ها.")

    # جستجوی هوشمند برای قیمت طلا (ممکن است نام در API تغییر کند)
    gold_price = 0
    for key in prices:
        if "۱۸ عیار" in key or "18 عیار" in key:
            gold_price = prices[key]
            break
    
    if gold_price > 0:
        result = rial_amount / gold_price
        text = f"⚖️ **تحلیل خرید با {toman_amount:,} تومان:**\n\n"
        text += f"🔸 معادل طلا: `{round(result, 3)}` گرم ۱۸ عیار\n"
        text += f"🔹 قیمت مبنا: `{gold_price:,}` ریال"
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("❌ متاسفانه قیمت طلای ۱۸ عیار در لیست یافت نشد.")
    
    await state.clear()

# اصلاح بخش حباب
@dp.message(F.text == "📊 محاسبه حباب سکه")
async def bubble_calc(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("خطا در دریافت اطلاعات.")
    text = "🧼 **حباب تقریبی سکه:**\n\n"
    for s in ["سکه تمام", "نیم سکه", "ربع سکه"]:
        p = prices.get(s, 0)
        if p > 0:
            text += f"🔸 {s}: `{int(p * 0.14):,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💰 قیمت‌های لحظه‌ای")
async def show_prices(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا.")
    text = f"🕒 **بروزرسانی:** {datetime.now(TIMEZONE).strftime('%H:%M')}\n\n"
    for k, v in list(prices.items())[:8]:
        text += f"🔹 {k}: `{v:,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

# --- سیستم هشدار اصلاح شده ---
@dp.message(F.text == "🔔 ثبت هشدار قیمت")
async def alert_menu(message: types.Message):
    builder = InlineKeyboardBuilder()
    items = ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه", "ربع سکه"]
    for item in items:
        builder.row(types.InlineKeyboardButton(text=item, callback_data=f"set:{item}"))
    await message.answer("🎯 آیتم مورد نظر را انتخاب کنید:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set:"))
async def alert_step2(callback: types.CallbackQuery, state: FSMContext):
    item = callback.data.split(":")[1]
    await state.update_data(item=item)
    await callback.message.edit_text(f"📉 قیمت هدف (به ریال) برای **{item}** را وارد کنید:")
    await state.set_state(BotStates.waiting_for_alert_value)

@dp.message(BotStates.waiting_for_alert_value)
async def alert_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ عدد نامعتبر.")
    data = await state.get_data()
    item, target = data['item'], int(message.text)
    alerts = load_alerts()
    uid = str(message.from_user.id)
    if uid not in alerts: alerts[uid] = {}
    alerts[uid][item] = target
    save_alerts(alerts)
    await message.answer(f"✅ ثبت شد. اگر {item} به {target:,} ریال برسد خبرتان می‌دهم.")
    await state.clear()

# --- تنظیمات Webhook و اتوماسیون (اصلاح شده) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # تنظیم مجدد وب‌هوک در هر بار اجرا
    await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH, drop_pending_updates=True)
    if not scheduler.running:
        # چک کردن هشدارها هر ۵ دقیقه
        scheduler.add_job(check_alerts_task, 'interval', minutes=5)
        # گزارش‌های ساعت ۱۲
        scheduler.add_job(auto_report, 'cron', hour=12, minute=0)
        scheduler.add_job(auto_report, 'cron', hour=0, minute=0)
        scheduler.start()
    yield
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)

@app.post(WEBHOOK_PATH)
async def bot_webhook(request: Request):
    update = Update.model_validate(await request.json(), context={"bot": bot})
    await dp.feed_update(bot, update)
    return {"ok": True}

@app.get("/")
async def health(): return {"status": "ok", "time": datetime.now(TIMEZONE).isoformat()}

async def check_alerts_task():
    prices = await get_prices()
    if not prices: return
    alerts = load_alerts()
    for uid, u_alerts in list(alerts.items()):
        for item, target in list(u_alerts.items()):
            current = prices.get(item, 0)
            if current > 0 and current <= target:
                try:
                    await bot.send_message(uid, f"🚨 **هشدار خرید!**\n{item} به قیمت `{current:,}` ریال رسید!")
                    del alerts[uid][item]
                except: pass
    save_alerts(alerts)

async def auto_report():
    prices = await get_prices()
    if prices:
        text = "📢 **گزارش بازار (ارسال خودکار)**\n\n"
        items = ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه"]
        for i in items:
            if i in prices: text += f"▪️ {i}: `{prices[i]:,}` ریال\n"
        try: await bot.send_message(GROUP_ID, text, parse_mode="Markdown")
        except: pass

import os
import asyncio
import logging
import json
from datetime import datetime
import pytz
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

# --- تنظیمات اختصاصی ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'
BASE_URL = "https://gold-w3ch.onrender.com" 
WEBHOOK_PATH = f"/bot/{API_TOKEN}"
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
scheduler = AsyncIOScheduler(timezone=TEHRAN_TZ)
DB_ALERTS = "alerts.json"

class BotStates(StatesGroup):
    waiting_for_convert = State()
    waiting_for_alert_value = State()

# --- توابع کمکی ---
def fa_to_en(number):
    """تبدیل اعداد فارسی به انگلیسی برای جلوگیری از خطا در محاسبات"""
    return str(number).translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789'))

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
                    # استخراج قیمت‌ها و تبدیل به ریال
                    return {item['title']: int(item['price']['sell'] * 1000) for item in data['prices']}
    except Exception as e:
        logging.error(f"Fetch Error: {e}")
    return None

# --- هندلرهای پیام ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="💰 قیمت‌های لحظه‌ای"), types.KeyboardButton(text="🔄 تبدیل‌گر واحد"))
    kb.row(types.KeyboardButton(text="🔔 ثبت هشدار قیمت"), types.KeyboardButton(text="📊 محاسبه حباب سکه"))
    await message.answer("💎 **دستیار هوشمند بازار طلا و سکه**\n\nوضعیت سرور: عملیاتی ✅\nزمان‌بندی: فعال 🕒", 
                         reply_markup=kb.as_markup(resize_keyboard=True))

@dp.message(F.text == "💰 قیمت‌های لحظه‌ای")
async def show_prices(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا در دریافت اطلاعات از بازار.")
    
    text = f"🕒 **بروزرسانی:** {datetime.now(TEHRAN_TZ).strftime('%H:%M:%S')}\n\n"
    for title, val in list(prices.items())[:7]:
        text += f"🔹 {title}: `{val:,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔄 تبدیل‌گر واحد")
async def converter_init(message: types.Message, state: FSMContext):
    await state.set_state(BotStates.waiting_for_convert)
    await message.answer("💸 مبلغ مورد نظر را به **تومان** وارد کنید:")

@dp.message(BotStates.waiting_for_convert)
async def converter_proc(message: types.Message, state: FSMContext):
    clean_text = fa_to_en(message.text.strip())
    if not clean_text.isdigit():
        return await message.answer("⚠️ لطفاً فقط عدد وارد کنید.")
    
    amount_toman = int(clean_text)
    amount_rial = amount_toman * 10
    prices = await get_prices()
    
    if not prices: return await message.answer("❌ خطا در دریافت قیمت‌ها.")

    # جستجوی هوشمند قیمت طلا و سکه
    gold_p = next((v for k, v in prices.items() if "۱۸ عیار" in k or "18 عیار" in k), 0)
    coin_p = next((v for k, v in prices.items() if "سکه تمام" in k), 0)

    if gold_p > 0:
        gold_res = amount_rial / gold_p
        coin_res = amount_rial / coin_p if coin_p > 0 else 0
        
        text = f"⚖️ **تحلیل خرید با {amount_toman:,} تومان:**\n\n"
        text += f"🔸 طلا ۱۸ عیار: `{round(gold_res, 3)}` گرم\n"
        if coin_res > 0: text += f"🔸 سکه تمام: `{round(coin_res, 2)}` عدد\n"
        text += f"\n🔹 قیمت مبنا: `{gold_p:,}` ریال"
        await message.answer(text, parse_mode="Markdown")
    else:
        await message.answer("❌ قیمت طلا در لیست یافت نشد.")
    await state.clear()

@dp.message(F.text == "📊 محاسبه حباب سکه")
async def bubble_calc(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا.")
    text = "🧼 **حباب تقریبی سکه:**\n\n"
    for s in ["سکه تمام", "نیم سکه", "ربع سکه"]:
        p = prices.get(s, 0)
        if p > 0: text += f"🔸 {s}: `{int(p * 0.14):,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "🔔 ثبت هشدار قیمت")
async def alert_menu(message: types.Message):
    builder = InlineKeyboardBuilder()
    for i in ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه", "ربع سکه"]:
        builder.row(types.InlineKeyboardButton(text=i, callback_data=f"set:{i}"))
    await message.answer("🎯 آیتم را برای دیده‌بانی انتخاب کنید:", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set:"))
async def alert_step2(callback: types.CallbackQuery, state: FSMContext):
    item = callback.data.split(":")[1]
    await state.update_data(item=item)
    await callback.message.edit_text(f"📉 قیمت هدف (**به ریال**) برای {item} را بفرستید:")
    await state.set_state(BotStates.waiting_for_alert_value)

@dp.message(BotStates.waiting_for_alert_value)
async def alert_final(message: types.Message, state: FSMContext):
    clean_val = fa_to_en(message.text.strip())
    if not clean_val.isdigit(): return await message.answer("⚠️ عدد نامعتبر.")
    
    data = await state.get_data()
    item, target = data['item'], int(clean_val)
    alerts = load_alerts()
    uid = str(message.from_user.id)
    if uid not in alerts: alerts[uid] = {}
    alerts[uid][item] = target
    save_alerts(alerts)
    
    await message.answer(f"✅ ثبت شد. به محض رسیدن {item} به {target:,} ریال خبرتان می‌دهم.")
    await state.clear()

# --- سیستم خودکار و سرور ---
async def check_alerts_task():
    prices = await get_prices()
    if not prices: return
    alerts = load_alerts()
    changed = False
    for uid, u_alerts in list(alerts.items()):
        for item, target in list(u_alerts.items()):
            # جستجوی منعطف برای هشدار
            current = next((v for k, v in prices.items() if item in k), 0)
            if current > 0 and current <= target:
                try:
                    await bot.send_message(uid, f"🚨 **هشدار خرید!**\n\n{item} به قیمت هدف شما ({target:,}) رسید.\nقیمت فعلی: `{current:,}` ریال")
                    del alerts[uid][item]
                    changed = True
                except: pass
    if changed: save_alerts(alerts)

async def auto_report():
    prices = await get_prices()
    if prices:
        text = "📢 **گزارش وضعیت بازار**\n\n"
        for i in ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه"]:
            p = next((v for k, v in prices.items() if i in k), 0)
            if p > 0: text += f"▪️ {i}: `{p:,}` ریال\n"
        try: await bot.send_message(GROUP_ID, text, parse_mode="Markdown")
        except Exception as e: logging.error(f"Group send error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(url=BASE_URL + WEBHOOK_PATH, drop_pending_updates=True)
    if not scheduler.running:
        scheduler.add_job(check_alerts_task, 'interval', minutes=5)
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
async def health(): return {"status": "active", "timezone": "Asia/Tehran"}

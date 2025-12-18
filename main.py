import os
import json
import logging
import asyncio
from datetime import datetime
import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- تنظیمات مستقیم (هماهنگ با درخواست شما) ---
API_TOKEN = '8363878660:AAHoIKwGNw1P32dot-atLmGtei2o65xTdgc'
GROUP_ID = -4843735218
API_URL = 'https://price.tlyn.ir/api/v1/price'

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# دیتابیس فایلی ساده (لوکال)
DB_ALERTS = "alerts.json"

class BotStates(StatesGroup):
    waiting_for_convert_amount = State()
    waiting_for_alert_price = State()

# --- توابع مدیریت داده (فایلی) ---
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
            async with session.get(API_URL, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # تبدیل لیست به دیکشنری برای دسترسی سریع
                    return {item['title']: item['price']['sell'] * 1000 for item in data['prices']}
    except: return None

# --- منوی اصلی ---
def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="💰 قیمت‌های لحظه‌ای"), types.KeyboardButton(text="🔄 تبدیل‌گر واحد"))
    kb.row(types.KeyboardButton(text="🔔 ثبت هشدار قیمت"), types.KeyboardButton(text="📊 محاسبه حباب سکه"))
    return kb.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("💎 **به ربات پیشرفته طلا و سکه خوش آمدید**\n\nاین ربات قیمت‌ها را ثانیه ای چک کرده و در ساعت ۱۲ به گروه ارسال می‌کند.", reply_markup=main_menu())

# --- ۱. نمایش قیمت‌ها ---
@dp.message(F.text == "💰 قیمت‌های لحظه‌ای")
async def show_prices(message: types.Message):
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا در اتصال به بازار.")
    
    text = f"🕒 **بروزرسانی:** {datetime.now().strftime('%H:%M:%S')}\n\n"
    for title, val in list(prices.items())[:6]:
        text += f"🔹 {title}: `{val:,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

# --- ۲. تبدیل‌گر واحد پیشرفته ---
@dp.message(F.text == "🔄 تبدیل‌گر واحد")
async def convert_start(message: types.Message, state: FSMContext):
    await message.answer("💸 مبلغ مورد نظر خود را به **تومان** وارد کنید:")
    await state.set_state(BotStates.waiting_for_convert_amount)

@dp.message(BotStates.waiting_for_convert_amount)
async def convert_process(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("⚠️ فقط عدد انگلیسی وارد کنید.")
    
    amount = int(message.text)
    prices = await get_prices()
    if not prices: return await message.answer("❌ خطا در دریافت قیمت.")

    g18 = prices.get("گرم طلا عیار ۱۸", 1) / 10
    coin = prices.get("سکه تمام", 1) / 10

    text = f"⚖️ **با مبلغ {amount:,} تومان می‌توان خرید:**\n\n"
    text += f"🔸 طلا ۱۸ عیار: `{round(amount/g18, 3)}` گرم\n"
    text += f"🔸 سکه تمام: `{round(amount/coin, 2)}` عدد\n"
    text += f"🔸 ربع سکه: `{round(amount/(prices.get('ربع سکه',1)/10), 2)}` عدد"
    
    await message.answer(text, parse_mode="Markdown")
    await state.clear()

# --- ۳. ثبت هشدار قیمت ---
@dp.message(F.text == "🔔 ثبت هشدار قیمت")
async def alert_init(message: types.Message):
    builder = InlineKeyboardBuilder()
    for item in ["گرم طلا عیار ۱۸", "سکه تمام", "نیم سکه", "ربع سکه"]:
        builder.row(types.InlineKeyboardButton(text=item, callback_data=f"set:{item}"))
    await message.answer("🎯 انتخاب کنید برای کدام مورد هشدار بدهم؟", reply_markup=builder.as_markup())

@dp.callback_query(F.data.startswith("set:"))
async def alert_step2(callback: types.CallbackQuery, state: FSMContext):
    item = callback.data.split(":")[1]
    await state.update_data(item=item)
    await callback.message.edit_text(f"📉 قیمت هدف برای **{item}** را به **ریال** وارد کنید:\n(مثال: 450000000)")
    await state.set_state(BotStates.waiting_for_alert_price)

@dp.message(BotStates.waiting_for_alert_price)
async def alert_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("⚠️ عدد نامعتبر است.")
    
    data = await state.get_data()
    item, price = data['item'], int(message.text)
    
    alerts = load_alerts()
    user_id = str(message.from_user.id)
    if user_id not in alerts: alerts[user_id] = {}
    alerts[user_id][item] = price
    save_alerts(alerts)
    
    await message.answer(f"✅ ثبت شد. اگر {item} به کمتر از {price:,} ریال رسید خبرتان می‌دهم.")
    await state.clear()

# --- ۴. حباب سکه و پاسخ هوشمند ---
@dp.message(F.text == "📊 محاسبه حباب سکه")
async def bubble_view(message: types.Message):
    prices = await get_prices()
    text = "🧼 **حباب تقریبی سکه در بازار:**\n\n"
    for s in ["سکه تمام", "نیم سکه", "ربع سکه"]:
        p = prices.get(s, 0)
        text += f"🔸 {s}: `{int(p * 0.14):,}` ریال\n"
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text)
async def smart_logic(message: types.Message):
    if "چطوری" in message.text: await message.reply("ممنون! آماده استعلام قیمت هستم.")
    else: await message.reply("لطفاً از دکمه‌های منو استفاده کنید 👇")

# --- ۵. وظایف خودکار (Schedules) ---
async def check_alerts_task():
    prices = await get_prices()
    if not prices: return
    alerts = load_alerts()
    for uid, user_alerts in list(alerts.items()):
        for item, target in list(user_alerts.items()):
            if item in prices and prices[item] <= target:
                try:
                    await bot.send_message(uid, f"🚨 **هشدار خرید!**\n{item} به قیمت {prices[item]:,} ریال رسید!")
                    del alerts[uid][item]
                except: pass
    save_alerts(alerts)

async def auto_report():
    prices = await get_prices()
    if not prices: return
    text = f"📢 **گزارش بازار (ساعت {datetime.now().hour})**\n\n"
    for k, v in list(prices.items())[:5]:
        text += f"▪️ {k}: `{v:,}` ریال\n"
    try:
        await bot.send_message(GROUP_ID, text, parse_mode="Markdown")
    except: pass

async def main():
    scheduler.add_job(check_alerts_task, 'interval', minutes=5)
    scheduler.add_job(auto_report, 'cron', hour=12, minute=0)
    scheduler.add_job(auto_report, 'cron', hour=0, minute=0)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

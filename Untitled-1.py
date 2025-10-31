import os
import sys
import subprocess
import sqlite3
import asyncio
import random
from datetime import datetime, timedelta, timezone

# ========================== 📦 АВТОУСТАНОВКА БИБЛИОТЕК ==========================
required_libs = [
    "aiogram==3.3.0",
    "python-dateutil"
]

for lib in required_libs:
    try:
        __import__(lib.split("==")[0])
    except ImportError:
        print(f"⚙️ Устанавливаю пакет: {lib} ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", lib])

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

# ========================== ⚙️ НАСТРОЙКИ ==========================
BOT_TOKEN = "8375240057:AAHmI5rg7YpYjbZGCxEzEBHVngzs6SgQZvA"
if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_СЮДА":
    raise ValueError("❌ BOT_TOKEN не задан. Укажи свой токен Telegram бота.")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

TZ = timezone(timedelta(hours=3))
LOVE_START_DATE = datetime(2024, 6, 1, tzinfo=TZ)

# ========================== 💾 БАЗА ДАННЫХ ==========================
def db_conn():
    conn = sqlite3.connect("lovebot.db")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS stats (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            popa_count INTEGER DEFAULT 0
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            remind_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            text TEXT,
            photo_id TEXT
        )
    """)
    conn.commit()
    return conn

# ========================== 📱 СОСТОЯНИЯ ==========================
class AddReminder(StatesGroup):
    waiting_text = State()
    waiting_time = State()

class AddNote(StatesGroup):
    waiting_text = State()
    waiting_photo = State()

class RandomRange(StatesGroup):
    waiting_min = State()
    waiting_max = State()

# ========================== 🧠 КНОПКИ ==========================
def main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💋 По попе")],
            [KeyboardButton(text="🕐 Напоминания"), KeyboardButton(text="📒 Заметки")],
            [KeyboardButton(text="🎲 Рандом"), KeyboardButton(text="📊 Статистика")]
        ],
        resize_keyboard=True
    )

# ========================== ❤️ СТАРТ ==========================
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("INSERT OR IGNORE INTO stats (user_id, name) VALUES (?, ?)", (message.from_user.id, message.from_user.full_name))
    conn.commit()
    conn.close()

    days_in_love = (datetime.now(TZ) - LOVE_START_DATE).days
    await message.answer(
        f"Привет, {message.from_user.first_name}! 💞\n"
        f"Вы уже вместе ❤️ {days_in_love} дней!",
        reply_markup=main_keyboard()
    )

# ========================== 💋 ПО ПОПЕ ==========================
@dp.message(F.text == "💋 По попе")
async def popa_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👩 Любимой", callback_data=f"popa_add_{message.from_user.id}_partner"),
                InlineKeyboardButton(text="👨 Любимому", callback_data=f"popa_add_{message.from_user.id}_me")
            ]
        ]
    )
    await message.answer("Кому добавить ‘по попе’? 😈", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("popa_add_"))
async def popa_add(query: types.CallbackQuery):
    parts = query.data.split("_")
    sender_id = int(parts[2])
    target = parts[3]

    conn = db_conn()
    cur = conn.cursor()

    if target == "me":
        cur.execute("UPDATE stats SET popa_count = popa_count + 1 WHERE user_id = ?", (sender_id,))
        target_name = "тебе 😏"
    else:
        cur.execute("UPDATE stats SET popa_count = popa_count + 1 WHERE user_id != ?", (sender_id,))
        target_name = "твоей любви 💞"

    conn.commit()
    conn.close()
    await query.answer(f"Добавлено {target_name} по попе 😈", show_alert=True)

# ========================== 🕐 НАПОМИНАНИЯ ==========================
@dp.message(F.text == "🕐 Напоминания")
async def reminders_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="reminder_add")],
            [InlineKeyboardButton(text="📋 Мои напоминания", callback_data="reminder_list")]
        ]
    )
    await message.answer("Меню напоминаний 🕐", reply_markup=keyboard)

@dp.callback_query(F.data == "reminder_add")
async def add_reminder_start(query: types.CallbackQuery, state):
    await query.message.answer("Напиши текст напоминания 📝")
    await state.set_state(AddReminder.waiting_text)

@dp.message(StateFilter(AddReminder.waiting_text))
async def add_reminder_text(message: types.Message, state):
    await state.update_data(text=message.text)
    await message.answer("Через сколько минут напомнить? ⏰")
    await state.set_state(AddReminder.waiting_time)

@dp.message(StateFilter(AddReminder.waiting_time))
async def add_reminder_time(message: types.Message, state):
    try:
        minutes = int(message.text)
    except ValueError:
        return await message.answer("Введи число минут, например 10")

    data = await state.get_data()
    remind_time = datetime.now(TZ) + timedelta(minutes=minutes)

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO reminders (user_id, text, remind_at) VALUES (?, ?, ?)",
                (message.from_user.id, data["text"], remind_time.isoformat()))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(f"Напоминание добавлено! 🕐 Через {minutes} минут.")

@dp.callback_query(F.data == "reminder_list")
async def reminder_list(query: types.CallbackQuery):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, text, remind_at FROM reminders WHERE user_id = ?", (query.from_user.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await query.message.answer("Нет активных напоминаний 💫")
    else:
        text = "📋 Твои напоминания:\n"
        for r in rows:
            remind_time = datetime.fromisoformat(r[2])
            text += f"🕐 {r[1]} — {remind_time.strftime('%H:%M %d.%m')}  /del_{r[0]}\n"
        await query.message.answer(text)

@dp.message(F.text.startswith("/del_"))
async def del_reminder(message: types.Message):
    reminder_id = message.text.replace("/del_", "")
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, message.from_user.id))
    conn.commit()
    conn.close()
    await message.answer("✅ Напоминание удалено.")

# ========================== 📒 ЗАМЕТКИ ==========================
@dp.message(F.text == "📒 Заметки")
async def notes_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить", callback_data="note_add")],
            [InlineKeyboardButton(text="📋 Мои заметки", callback_data="note_list")]
        ]
    )
    await message.answer("Меню заметок 📒", reply_markup=keyboard)

# (остальная часть кода из твоего предыдущего варианта остаётся без изменений)
# ...

# ========================== 🚀 ЗАПУСК ==========================
async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

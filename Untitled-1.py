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
            [KeyboardButton("💋 По попе")],
            [KeyboardButton("🕐 Напоминания"), KeyboardButton("📒 Заметки")],
            [KeyboardButton("🎲 Рандом"), KeyboardButton("📊 Статистика")]
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

@dp.callback_query(F.data == "note_add")
async def add_note_start(query: types.CallbackQuery, state):
    await query.message.answer("Отправь текст заметки 📝")
    await state.set_state(AddNote.waiting_text)

@dp.message(StateFilter(AddNote.waiting_text))
async def add_note_text(message: types.Message, state):
    await state.update_data(text=message.text)
    await message.answer("Хочешь добавить фото к заметке? (да/нет)")
    await state.set_state(AddNote.waiting_photo)

@dp.message(StateFilter(AddNote.waiting_photo))
async def add_note_photo(message: types.Message, state):
    data = await state.get_data()
    photo_id = None
    if message.photo:
        photo_id = message.photo[-1].file_id

    conn = db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO notes (user_id, text, photo_id) VALUES (?, ?, ?)",
                (message.from_user.id, data["text"], photo_id))
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer("✅ Заметка сохранена.")

@dp.callback_query(F.data == "note_list")
async def note_list(query: types.CallbackQuery):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, text, photo_id FROM notes WHERE user_id = ?", (query.from_user.id,))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        await query.message.answer("Нет заметок 📭")
    else:
        for n in rows:
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Удалить", callback_data=f"note_del_{n[0]}")]
            ])
            if n[2]:
                await bot.send_photo(query.from_user.id, n[2], caption=n[1], reply_markup=kb)
            else:
                await bot.send_message(query.from_user.id, n[1], reply_markup=kb)

@dp.callback_query(F.data.startswith("note_del_"))
async def note_delete(query: types.CallbackQuery):
    note_id = query.data.replace("note_del_", "")
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, query.from_user.id))
    conn.commit()
    conn.close()
    await query.answer("🗑️ Заметка удалена", show_alert=True)

# ========================== 🎲 РАНДОМ ==========================
@dp.message(F.text == "🎲 Рандом")
async def random_start(message: types.Message, state):
    await message.answer("Введи минимальное число 🎯")
    await state.set_state(RandomRange.waiting_min)

@dp.message(StateFilter(RandomRange.waiting_min))
async def random_min(message: types.Message, state):
    try:
        val = int(message.text)
    except ValueError:
        return await message.answer("Введи число")
    await state.update_data(min=val)
    await message.answer("Теперь введи максимальное число 🎯")
    await state.set_state(RandomRange.waiting_max)

@dp.message(StateFilter(RandomRange.waiting_max))
async def random_max(message: types.Message, state):
    try:
        val = int(message.text)
    except ValueError:
        return await message.answer("Введи число")

    data = await state.get_data()
    res = random.randint(data["min"], val)
    await message.answer(f"🎲 Случайное число: {res}")
    await state.clear()

# ========================== 📊 СТАТИСТИКА ==========================
@dp.message(F.text == "📊 Статистика")
async def stats(message: types.Message):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT name, popa_count FROM stats WHERE user_id = ?", (message.from_user.id,))
    user = cur.fetchone()
    conn.close()

    days = (datetime.now(TZ) - LOVE_START_DATE).days
    popa_count = user[1] if user else 0
    await message.answer(f"❤️ {user[0]}\n💋 По попе: {popa_count}\n📅 Вместе: {days} дней")

# ========================== 🕐 ПРОВЕРКА НАПОМИНАНИЙ ==========================
async def reminder_loop():
    while True:
        now = datetime.now(TZ)
        conn = db_conn()
        cur = conn.cursor()
        cur.execute("SELECT id, user_id, text FROM reminders WHERE remind_at <= ?", (now.isoformat(),))
        rows = cur.fetchall()
        for r in rows:
            await bot.send_message(r[1], f"🔔 Напоминание: {r[2]}")
            cur.execute("DELETE FROM reminders WHERE id = ?", (r[0],))
        conn.commit()
        conn.close()
        await asyncio.sleep(60)

# ========================== 🚀 ЗАПУСК ==========================
async def main():
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

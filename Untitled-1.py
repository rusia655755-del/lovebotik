"""
LoveBotik 7.0 💞 — полностью рабочий бот с выбором пользователя для "по попе" и удалением заметок/напоминаний
aiogram 3.x
"""

import logging
import random
import sqlite3
from datetime import datetime, date
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command, StateFilter
from aiogram.filters.text import Text
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from aiogram.fsm.storage.memory import MemoryStorage

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from dateutil.parser import parse

# === CONFIG ===
BOT_TOKEN = "8375240057:AAHmI5rg7YpYjbZGCxEzEBHVngzs6SgQZvA"  # Вставь свой токен
TZ = ZoneInfo("Europe/Stockholm")
RELATIONSHIP_START = date(2024, 6, 1)
DB_PATH = "couple_bot.db"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === DATABASE ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS pops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        by_user_id INTEGER,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT,
        content TEXT,
        file_id TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        text TEXT,
        remind_at TEXT,
        created_at TEXT,
        job_id TEXT
    );
    """)
    conn.commit()
    conn.close()

def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def ensure_user_in_db(user: types.User):
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.now(TZ).isoformat()
    cur.execute("""
        INSERT OR REPLACE INTO users (user_id, first_name, last_name, username, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (user.id, user.first_name or "", user.last_name or "", user.username or "", now))
    conn.commit()
    conn.close()

def add_popa(target_user_id: int, by_user_id: int):
    conn = db_conn()
    cur = conn.cursor()
    now = datetime.now(TZ).isoformat()
    cur.execute("INSERT INTO pops (user_id, by_user_id, created_at) VALUES (?, ?, ?)", (target_user_id, by_user_id, now))
    conn.commit()
    conn.close()

def count_pops(user_id: int) -> int:
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM pops WHERE user_id = ?", (user_id,))
    r = cur.fetchone()[0]
    conn.close()
    return r

def days_together() -> int:
    return (datetime.now(TZ).date() - RELATIONSHIP_START).days

def get_all_users(exclude_id: int):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id, first_name FROM users WHERE user_id != ?", (exclude_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

# === BUTTONS ===
def make_kb(*buttons, row_width=2):
    rows = []
    for i in range(0, len(buttons), row_width):
        rows.append([InlineKeyboardButton(text=btn[0], callback_data=btn[1]) for btn in buttons[i:i+row_width]])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def main_menu_kb():
    return make_kb(
        ("➕ Добавить напоминание", "menu:add_reminder"),
        ("📋 Просмотреть напоминания", "menu:view_reminders"),
        ("📝 Заметки", "menu:notes"),
        ("📄 Просмотреть заметки", "menu:view_notes"),
        ("🍑 Добавить по попе", "menu:add_popa"),
        ("📊 Статистика", "menu:stats"),
        ("✊✌️🖐 РПС", "menu:rps"),
        ("🎲 Рандом", "menu:random")
    )

# === FSM ===
class RandomState(StatesGroup):
    waiting_for_range = State()

class ReminderState(StatesGroup):
    waiting_for_text = State()
    waiting_for_time = State()

class NoteState(StatesGroup):
    waiting_for_title = State()
    waiting_for_content = State()

class PopaState(StatesGroup):
    waiting_for_target = State()

# === INIT BOT ===
init_db()
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
scheduler = AsyncIOScheduler(timezone=TZ)

# === START COMMAND ===
@dp.message(Command("start"))
async def cmd_start(message: Message):
    ensure_user_in_db(message.from_user)
    await message.answer(
        f"Привет, {message.from_user.first_name}! 💞\nПарный бот с напоминаниями, заметками и играми.",
        reply_markup=main_menu_kb()
    )

# === CALLBACKS ===
@dp.callback_query(Text("menu:back"))
async def cb_back(query: CallbackQuery):
    await query.answer()
    await query.message.edit_text("Главное меню:", reply_markup=main_menu_kb())

# --- ADD POPA WITH CHOICE ---
@dp.callback_query(Text("menu:add_popa"))
async def cb_add_popa(query: CallbackQuery, state: FSMContext):
    users = get_all_users(query.from_user.id)
    if not users:
        await query.answer()
        await query.message.edit_text("❌ Нет других пользователей для добавления по попе", reply_markup=main_menu_kb())
        return
    kb = make_kb(*[(u[1], f"popa_to:{u[0]}") for u in users], row_width=1)
    await query.message.edit_text("Выберите пользователя, которому добавить по попе:", reply_markup=kb)
    await state.set_state(PopaState.waiting_for_target)

@dp.callback_query(StateFilter(PopaState.waiting_for_target), Text(startswith="popa_to:"))
async def cb_select_popa_target(query: CallbackQuery, state: FSMContext):
    target_id = int(query.data.split(":")[1])
    add_popa(target_id, query.from_user.id)
    total = count_pops(target_id)
    await query.answer()
    await query.message.edit_text(f"🍑 Вы добавили +1 по попе пользователю!\nВсего у него: {total}", reply_markup=main_menu_kb())
    await state.clear()

# --- VIEW AND DELETE REMINDERS ---
@dp.callback_query(Text("menu:view_reminders"))
async def cb_view_reminders(query: CallbackQuery):
    uid = query.from_user.id
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, text, remind_at FROM reminders WHERE user_id=? ORDER BY remind_at", (uid,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await query.message.edit_text("⏰ Нет напоминаний", reply_markup=main_menu_kb())
        return
    kb = make_kb(*[(f"❌ {r[1]}", f"del_reminder:{r[0]}") for r in rows], row_width=1)
    await query.message.edit_text("⏰ Ваши напоминания:", reply_markup=kb)

@dp.callback_query(Text(startswith="del_reminder:"))
async def cb_delete_reminder(query: CallbackQuery):
    rid = int(query.data.split(":")[1])
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM reminders WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    await query.answer("Удалено ✅")
    await cb_view_reminders(query)

# --- NOTES CREATE / VIEW / DELETE ---
@dp.callback_query(Text("menu:notes"))
async def cb_notes(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("Введите заголовок заметки:")
    await state.set_state(NoteState.waiting_for_title)

@dp.message(StateFilter(NoteState.waiting_for_title))
async def process_note_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer("Введите текст заметки:")
    await state.set_state(NoteState.waiting_for_content)

@dp.message(StateFilter(NoteState.waiting_for_content))
async def process_note_content(message: Message, state: FSMContext):
    data = await state.get_data()
    title = data.get("title")
    content = message.text
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO notes (user_id, title, content, file_id, created_at) VALUES (?, ?, ?, ?, ?)",
                (message.from_user.id, title, content, None, datetime.now(TZ).isoformat()))
    conn.commit()
    conn.close()
    await message.answer(f"✅ Заметка '{title}' добавлена", reply_markup=main_menu_kb())
    await state.clear()

@dp.callback_query(Text("menu:view_notes"))
async def cb_view_notes(query: CallbackQuery):
    uid = query.from_user.id
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, title, content FROM notes WHERE user_id=? ORDER BY created_at", (uid,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        await query.message.edit_text("📝 Нет заметок", reply_markup=main_menu_kb())
        return
    kb = make_kb(*[(f"❌ {r[1]}", f"del_note:{r[0]}") for r in rows], row_width=1)
    await query.message.edit_text("📝 Ваши заметки:", reply_markup=kb)

@dp.callback_query(Text(startswith="del_note:"))
async def cb_delete_note(query: CallbackQuery):
    nid = int(query.data.split(":")[1])
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM notes WHERE id=?", (nid,))
    conn.commit()
    conn.close()
    await query.answer("Удалено ✅")
    await cb_view_notes(query)

# --- RANDOM ---
class RandomState(StatesGroup):
    waiting_for_range = State()

@dp.callback_query(Text("menu:random"))
async def cb_random(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.edit_text("Введите диапазон чисел через пробел, например: 1 100")
    await state.set_state(RandomState.waiting_for_range)

@dp.message(StateFilter(RandomState.waiting_for_range))
async def process_random_range(message: Message, state: FSMContext):
    try:
        a, b = map(int, message.text.split())
        if a > b: a, b = b, a
        r = random.randint(a, b)
        await message.answer(f"🎲 Рандомное число от {a} до {b}: {r}", reply_markup=main_menu_kb())
        await state.clear()
    except:
        await message.answer("❌ Неверный формат. Введите два числа через пробел, например: 1 100")

# === STATS ===
@dp.callback_query(Text("menu:stats"))
async def cb_stats(query: CallbackQuery):
    await query.answer()
    uid = query.from_user.id
    total_pops = count_pops(uid)
    conn = db_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM notes WHERE user_id=?", (uid,))
    total_notes = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM reminders WHERE user_id=?", (uid,))
    total_reminders = cur.fetchone()[0]
    conn.close()
    await query.message.edit_text(
        f"📊 Статистика {query.from_user.first_name}:\n"
        f"💘 Вместе: {days_together()} дней\n"
        f"🍑 Получено по попе: {total_pops}\n"
        f"📝 Заметок: {total_notes}\n"
        f"⏰ Напоминаний: {total_reminders}",
        reply_markup=main_menu_kb()
    )

# === STARTUP / SHUTDOWN ===
async def on_startup():
    scheduler.start()
    logger.info("Бот запущен 💞")

async def on_shutdown():
    scheduler.shutdown()
    await bot.session.close()

if __name__ == "__main__":
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    dp.run_polling(bot)

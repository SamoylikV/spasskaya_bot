import asyncio
import logging
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.filters import Command, CommandObject
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TOKEN, ADMIN_ID, DB_URL
from db.db import create_appeal, add_message, get_appeals, update_status, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


class AdminReply(StatesGroup):
    waiting_text = State()


class RoomInput(StatesGroup):
    waiting_room = State()


class UserAppeal(StatesGroup):
    waiting_text = State()



async def show_main_menu(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Обращение (ресепшен)", callback_data="menu_appeal")],
        # [InlineKeyboardButton(text="🛎 Бронирование (пока недоступно)", callback_data="menu_booking")],
        [InlineKeyboardButton(text="📞 Контакты", callback_data="menu_contacts")]
    ])
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=keyboard)


async def show_user_menu_after_room(message: Message, state: FSMContext):
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛏 Убраться в номере")],
            [KeyboardButton(text="🍴 Принести еду")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await state.set_state(UserAppeal.waiting_text)
    await message.answer("Напишите ваше обращение или выберите из готовых вариантов:", reply_markup=keyboard)


@router.message(Command("start"))
async def start(message: Message, command: CommandObject, state: FSMContext):
    args = command.args
    if args and args.isdigit():
        await state.update_data(room=args)
        await show_user_menu_after_room(message, state)
        return

    await show_main_menu(message)


@router.callback_query(F.data == "menu_appeal")
async def menu_appeal(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    room = data.get("room")
    if room:
        await show_user_menu_after_room(callback.message, state)
    else:
        await callback.message.answer("Введите номер комнаты (числом):")
        await state.set_state(RoomInput.waiting_room)


@router.callback_query(F.data == "menu_booking")
async def menu_booking(callback: CallbackQuery):
    await callback.answer("Функция бронирования пока не реализована.", show_alert=True)


@router.callback_query(F.data == "menu_contacts")
async def menu_contacts(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("Контакты отеля:\n📞 +7 (812) 000-00-00\n📍 Адрес: ул. Спасская, д.1\n🌐 Сайт: https://spasskaya.example")


@router.message(RoomInput.waiting_room)
async def get_room(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Номер комнаты должен быть числом. Попробуйте ещё раз или отправьте /cancel.")
        return
    await state.update_data(room=message.text)
    await show_user_menu_after_room(message, state)


@router.message(Command("cancel"))
async def cancel_cmd(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Операция отменена. Если нужно — начните заново /start.")


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Это бот отеля 'Спасская'.\n"
                         "/start — главное меню\n"
                         "/admin — меню администратора (только для админа)\n"
                         "/cancel — отменить текущее действие\n"
                         "Для обращения сначала укажите номер комнаты через /start 101 или при запросе.")


# @router.callback_query(F.data.startswith("task_"))
# async def task_chosen(callback: CallbackQuery, state: FSMContext):
#     await callback.answer()
#     user_id = callback.from_user.id
#     username = callback.from_user.username or str(user_id)
#     data = await state.get_data()
#     room = data.get("room", "не указан")

#     text_map = {
#         "task_clean": "Убраться в номере",
#         "task_food": "Принести еду",
#         "task_other": "Другое обращение"
#     }
#     key = callback.data
#     text = text_map.get(key, "Другое обращение")

#     appeal_id = await create_appeal(user_id, username, room, text)
#     await add_message(appeal_id, "user", text)

#     keyboard = InlineKeyboardMarkup(inline_keyboard=[
#         [
#             InlineKeyboardButton(text="✅ Получено", callback_data=f"admin_status:{appeal_id}:received"),
#             InlineKeyboardButton(text="❌ Отказано", callback_data=f"admin_status:{appeal_id}:declined"),
#             InlineKeyboardButton(text="✔ Выполнено", callback_data=f"admin_status:{appeal_id}:done"),
#             InlineKeyboardButton(text="✉ Ответить", callback_data=f"admin_reply:{appeal_id}")
#         ]
#     ])

#     await bot.send_message(ADMIN_ID, f"📩 Новое обращение от @{username} (комната {room})\n📝 {text}", reply_markup=keyboard)
#     await callback.message.answer("Ваше обращение отправлено ✅")

@router.message(UserAppeal.waiting_text)
async def user_appeal_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    data = await state.get_data()
    room = data.get("room", "не указан")

    text = message.text.strip()

    appeal_id = await create_appeal(user_id, username, room, text)
    await add_message(appeal_id, "user", text)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Получено", callback_data=f"admin_status:{appeal_id}:received"),
            InlineKeyboardButton(text="❌ Отказано", callback_data=f"admin_status:{appeal_id}:declined"),
            InlineKeyboardButton(text="✔ Выполнено", callback_data=f"admin_status:{appeal_id}:done"),
            InlineKeyboardButton(text="✉ Ответить", callback_data=f"admin_reply:{appeal_id}")
        ]
    ])

    await bot.send_message(
        ADMIN_ID,
        f"📩 Новое обращение от @{username} (комната {room})\n📝 {text}",
        reply_markup=keyboard
    )

    await message.answer("Ваше обращение отправлено ✅", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@router.message(Command("admin"))
async def admin_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📂 Все обращения", callback_data="admin_all")],
        [InlineKeyboardButton(text="📂 Только открытые", callback_data="admin_open")],
        [InlineKeyboardButton(text="📂 Только закрытые", callback_data="admin_closed")],
        [InlineKeyboardButton(text="ℹ Статистика", callback_data="admin_stats")]
    ])
    await message.answer("Админ меню:", reply_markup=keyboard)


@router.callback_query(F.data.in_(["admin_all", "admin_open", "admin_closed", "admin_stats"]))
async def show_appeals(callback: CallbackQuery):
    await callback.answer()
    if callback.data == "admin_stats":
        conn = await asyncpg.connect(DB_URL)
        try:
            total = await conn.fetchval("SELECT COUNT(*) FROM appeals")
            open_cnt = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='new'")
            done_cnt = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='done'")
        finally:
            await conn.close()
        await callback.message.answer(f"Статистика\nВсего: {total}\nОткрытых: {open_cnt}\nЗакрытых: {done_cnt}")
        return

    status = None
    if callback.data == "admin_open":
        status = "new"
    elif callback.data == "admin_closed":
        status = "done"

    appeals = await get_appeals(status=status)
    if not appeals:
        await callback.message.answer("Обращений нет.")
        return
    for a in appeals:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Получено", callback_data=f"admin_status:{a['id']}:received"),
                InlineKeyboardButton(text="❌ Отказано", callback_data=f"admin_status:{a['id']}:declined"),
                InlineKeyboardButton(text="✔ Выполнено", callback_data=f"admin_status:{a['id']}:done"),
                InlineKeyboardButton(text="✉ Ответить", callback_data=f"admin_reply:{a['id']}")
            ]
        ])
        created = a["created_at"]
        created_str = created.strftime("%Y-%m-%d %H:%M:%S") if isinstance(created, datetime) else str(created)
        await callback.message.answer(
            f"📨 ID:{a['id']} | @{a['username']} | Комната: {a['room']}\n📝 {a['text']}\n📌 Статус: {a['status']}\n📅 {created_str}",
            reply_markup=keyboard
        )


@router.callback_query(F.data.startswith("admin_status:"))
async def admin_set_status(callback: CallbackQuery):
    await callback.answer()
    try:
        _, appeal_id, status = callback.data.split(":")
    except ValueError:
        await callback.message.answer("Неправильный формат команды.")
        return

    try:
        appeal_id = int(appeal_id)
    except ValueError:
        await callback.message.answer("Неправильный ID обращения.")
        return

    user_id = await update_status(appeal_id, status)
    if user_id:
        if status == "done":
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❗ Вопрос не решили", callback_data=f"user_reopen:{appeal_id}")]
            ])
            await bot.send_message(user_id, f"Ваше обращение закрыто как '{status}'", reply_markup=keyboard)
        else:
            await bot.send_message(user_id, f"Статус вашего обращения изменён: {status}")
    await callback.message.answer(f"Статус обращения {appeal_id} обновлён на {status}.")


@router.callback_query(F.data.startswith("user_reopen:"))
async def user_reopen(callback: CallbackQuery):
    await callback.answer()
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        await callback.message.answer("Неправильный ID.")
        return
    await update_status(appeal_id, "new")
    await bot.send_message(ADMIN_ID, f"⚠ Пользователь переоткрыл обращение ID {appeal_id}")
    await callback.message.answer("Мы снова передали ваше обращение администратору ✅")


@router.callback_query(F.data.startswith("admin_reply:"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        await callback.message.answer("Неправильный ID обращения.")
        return
    await state.update_data(appeal_id=appeal_id)
    await callback.message.answer("Введите текст ответа пользователю:")
    await state.set_state(AdminReply.waiting_text)


@router.message(AdminReply.waiting_text)
async def send_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    appeal_id = data.get("appeal_id")
    if not appeal_id:
        await message.answer("ID обращения не найден. Пожалуйста, заново выберите обращение через /admin.")
        await state.clear()
        return

    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow("SELECT user_id FROM appeals WHERE id=$1", appeal_id)
    finally:
        await conn.close()

    if not row:
        await message.answer("Пользователь не найден.")
        await state.clear()
        return

    user_id = row["user_id"]
    await bot.send_message(user_id, f"📢 Сообщение от администратора:\n\n{message.text}")
    await add_message(appeal_id, "admin", message.text)
    await state.clear()
    await message.answer("Сообщение отправлено пользователю ✅")


@dp.errors()
async def global_error_handler(event, data):
    exception = data.get('exception')
    logger.exception("Ошибка при обработке апдейта: %s", exception)


async def main():
    logger.info("Инициализация БД...")
    await init_db()
    logger.info("Запуск polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
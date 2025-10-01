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
from db.db import create_appeal, add_message, get_appeals, update_status, init_db, is_admin, add_admin
from bot.admin_panel import admin_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
dp.include_router(admin_router)


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




@dp.errors()
async def global_error_handler(event, data):
    exception = data.get('exception')
    logger.exception("Ошибка при обработке апдейта: %s", exception)


async def main():
    logger.info("Инициализация БД...")
    await init_db()
    
    try:
        if ADMIN_ID:
            await add_admin(int(ADMIN_ID), "main_admin", "super_admin")
            logger.info(f"Главный админ {ADMIN_ID} добавлен в систему")
    except Exception as e:
        logger.warning(f"Не удалось добавить главного админа: {e}")
    
    logger.info("Запуск polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
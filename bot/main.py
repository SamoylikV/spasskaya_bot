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
from config import TOKEN, DB_URL
from db.db import create_appeal, add_message, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)


class RoomInput(StatesGroup):
    waiting_room = State()


class UserAppeal(StatesGroup):
    waiting_text = State()
    waiting_reply = State()


async def show_main_menu(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Обращение (ресепшен)", callback_data="menu_appeal")],
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
    help_text = """🏨 <b>Бот отеля 'Спасская'</b>

📋 <b>Команды:</b>
/start — главное меню
/help — получить справку
/cancel — отменить текущее действие

📩 <b>Как сделать обращение:</b>
1. Нажмите /start или выберите "Обращение (ресепшен)"
2. Укажите номер вашей комнаты
3. Опишите вашу проблему или пожелание

💬 <b>Ответы на сообщения:</b>
• Когда администратор ответит, вы сможете ответить обратно
• Нажмите кнопку "Ответить" под сообщением
• Напишите ваш ответ и отправьте

🔄 <b>Если проблема не решена:</b>
Нажмите "Не решено" под сообщением о выполнении

📞 <b>Быстрый старт:</b>
Можно сразу указать комнату: /start 101"""
    
    await message.answer(help_text, parse_mode="HTML")


@router.message(UserAppeal.waiting_text)
async def user_appeal_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    data = await state.get_data()
    room = data.get("room", "не указан")

    text = message.text.strip()

    appeal_id = await create_appeal(user_id, username, room, text)
    await add_message(appeal_id, "user", text)

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
    
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("UPDATE appeals SET status = 'new' WHERE id = $1", appeal_id)
    finally:
        await conn.close()
        
    await callback.message.answer("Мы снова передали ваше обращение администратору ✅")


@router.callback_query(F.data.startswith("user_reply:"))
async def user_start_reply(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        await callback.message.answer("Неправильный ID.")
        return
    
    await state.update_data(reply_appeal_id=appeal_id)
    await state.set_state(UserAppeal.waiting_reply)
    
    await callback.message.answer(
        "✏️ Напишите ваш ответ администратору:\n\n"
        "Отправьте /cancel чтобы отменить ответ."
    )


@router.message(UserAppeal.waiting_reply)
async def user_reply_text(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    appeal_id = data.get("reply_appeal_id")
    
    if not appeal_id:
        await message.answer("❌ Ошибка: ID обращения не найден. Попробуйте снова.")
        await state.clear()
        return
    
    text = message.text.strip()
    
    await add_message(appeal_id, "user", text)
    
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal = await conn.fetchrow("SELECT username, room FROM appeals WHERE id = $1", appeal_id)
        if appeal:
            await conn.execute(
                "UPDATE appeals SET status = 'new', updated_at = NOW() WHERE id = $1 AND status != 'new'", 
                appeal_id
            )
            
            logger.info(f"New user reply on appeal {appeal_id}: {text}")
            logger.info(f"Appeal {appeal_id} status updated to 'new' due to user reply")
    finally:
        await conn.close()
    
    await message.answer("✅ Ваш ответ отправлен администратору!")
    await state.clear()


@dp.errors()
async def global_error_handler(event, data):
    exception = data.get('exception')
    logger.exception("Ошибка при обработке апдейта: %s", exception)


async def check_message_queue():
    while True:
        try:
            conn = await asyncpg.connect(DB_URL)
            try:
                pending_messages = await conn.fetch(
                    """SELECT id, user_id, message, appeal_id, created_at 
                       FROM pending_admin_messages 
                       WHERE sent = FALSE 
                       AND created_at <= NOW() - INTERVAL '2 seconds'
                       ORDER BY created_at LIMIT 10"""
                )
                
                for msg in pending_messages:
                    try:

                        await conn.execute(
                            "UPDATE pending_admin_messages SET sent = TRUE WHERE id = $1",
                            msg['id']
                        )
                        
                        message_text = msg['message']
                        reply_markup = None
                        
                        if msg['appeal_id']:
                            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                            buttons = []
                            
                            if 'Ответ администратора' in message_text or 'Ваше обращение' in message_text:
                                buttons.append([InlineKeyboardButton(text="✏️ Ответить", callback_data=f"user_reply:{msg['appeal_id']}")])
                            
                            if 'выполнено ✅' in message_text:
                                buttons.append([InlineKeyboardButton(text="❌ Не решено", callback_data=f"user_reopen:{msg['appeal_id']}")])
                            
                            if buttons:
                                reply_markup = InlineKeyboardMarkup(inline_keyboard=buttons)
                        
                        await bot.send_message(
                            msg['user_id'],
                            message_text,
                            reply_markup=reply_markup
                        )
                        
                        logger.info(f"Sent admin message to user {msg['user_id']}")
                        
                    except Exception as e:
                        logger.error(f"Failed to send message to user {msg['user_id']}: {e}")

                        try:
                            await conn.execute(
                                "UPDATE pending_admin_messages SET sent = FALSE WHERE id = $1",
                                msg['id']
                            )
                        except Exception as rollback_error:
                            logger.error(f"Failed to rollback message status: {rollback_error}")
                        
            finally:
                await conn.close()
                
        except Exception as e:
            logger.error(f"Error checking message queue: {e}")
        
        await asyncio.sleep(5)

async def main():
    logger.info("Инициализация БД...")
    await init_db()
    
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_admin_messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                appeal_id INTEGER,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    finally:
        await conn.close()
    
    logger.info("Запуск polling и проверки очереди сообщений...")
    asyncio.create_task(check_message_queue())
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
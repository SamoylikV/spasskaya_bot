import asyncio
import logging
import asyncpg
from datetime import datetime
from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, FSInputFile
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
    waiting_comment = State()
    waiting_custom_problem = State()


async def show_main_menu(message: Message):
    await send_welcome_with_photo(message)
    await message.answer("Введите номер вашей комнаты:")


async def show_service_menu(message: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🧹 Нужен утюг и гладильная доска", callback_data="service_iron")],
        [InlineKeyboardButton(text="👕 Услуги прачечной", callback_data="service_laundry")],
        [InlineKeyboardButton(text="🔧 Техническая проблема в номере", callback_data="service_technical")],
        [InlineKeyboardButton(text="🍽 Услуги ресторана", callback_data="service_restaurant")],
        [InlineKeyboardButton(text="❓ Другой вопрос", callback_data="service_other")],
        [InlineKeyboardButton(text="📞 Контакты", callback_data="menu_contacts"), InlineKeyboardButton(text="🏠 Назад в главное меню", callback_data="back_main_menu")]
    ])
    await message.answer("Выберите услугу:", reply_markup=keyboard)


@router.message(Command("start"))
async def start(message: Message, command: CommandObject, state: FSMContext):
    args = command.args
    if args and args.isdigit():
        await state.update_data(room=args)
        await send_welcome_with_photo(message)
        await show_service_menu(message, state)
        return

    await show_main_menu(message)
    await state.set_state(RoomInput.waiting_room)

async def send_welcome_with_photo(message: Message):
    welcome_text = """
🏨 Добро пожаловать в отель "Спасская"!

Мы рады приветствовать вас в нашем боте. Здесь вы можете:

🛎 Заказать услуги номера
🍽 Ознакомиться с меню ресторана
🔧 Сообщить о технических проблемах
📞 Связаться с нашими службами

Для начала работы укажите номер вашей комнаты.
"""
    
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        photo_path = os.path.join(current_dir, '..', 'images', 'hotel_welcome.jpg')
        photo_path = os.path.abspath(photo_path)

        logger.info(f"Looking for photo at: {photo_path}")
        logger.info(f"Photo exists: {os.path.exists(photo_path)}")

        if os.path.exists(photo_path):
            photo = FSInputFile(photo_path)
            await message.answer_photo(photo, caption=welcome_text)
            logger.info("Photo sent successfully")
        else:
            logger.warning(f"Photo not found at {photo_path}")
            await message.answer(welcome_text)
    except Exception as e:
        logger.error(f"Error sending photo: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        await message.answer(welcome_text)


@router.callback_query(F.data == "back_main_menu")
async def back_main_menu(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await show_main_menu(callback.message)
    await state.set_state(RoomInput.waiting_room)


@router.callback_query(F.data == "menu_contacts")
async def menu_contacts(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    contacts_text = """
📞 Контакты отеля:
+7 (345) 255-00-08
8 800 700-55-08

📞 Ресепшн: вн. 101
🍽 Ресторан: вн. 122

🌐 Сайт: hotel-spasskaya.ru
📧 Почта: info@hotel-spasskaya.ru
"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад к услугам", callback_data="back_services")]
    ])
    await callback.message.answer(contacts_text, reply_markup=keyboard)


@router.message(RoomInput.waiting_room)
async def get_room(message: Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.answer("❌ Номер комнаты должен быть. Попробуйте ещё раз или отправьте /cancel.")
        return
    await state.update_data(room=message.text)
    await message.answer(f"✅ Номер комнаты: {message.text}")
    await show_service_menu(message, state)


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


async def create_service_request(user_id, username, room, service_type, description, optional_comment=None):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal_id = await conn.fetchval(
            "INSERT INTO appeals (user_id, username, room, text, request_type, optional_comment) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, username, room, description, service_type, optional_comment
        )
        await add_message(appeal_id, "user", description)
        if optional_comment:
            await add_message(appeal_id, "user", f"Комментарий: {optional_comment}")
    finally:
        await conn.close()
    return appeal_id

async def ask_for_comment(message: Message, state: FSMContext, service_text: str, service_type: str):
    await state.update_data(service_text=service_text, service_type=service_type)
    await state.set_state(UserAppeal.waiting_comment)
    await message.answer(f"{service_text}\n\nМожете добавить комментарий (необязательно):")

@router.callback_query(F.data == "service_iron")
async def service_iron(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Спасибо за обращение, уже несем!"
    await ask_for_comment(callback.message, state, response_text, "iron")

@router.callback_query(F.data == "service_laundry")
async def service_laundry(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Спасибо за обращение, мы свяжемся с вами в ближайшее время."
    await ask_for_comment(callback.message, state, response_text, "laundry")

@router.callback_query(F.data == "service_technical")
async def service_technical(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❄️ Кондиционер", callback_data="tech_ac")],
        [InlineKeyboardButton(text="📶 WiFi", callback_data="tech_wifi")],
        [InlineKeyboardButton(text="📺 Телевизор", callback_data="tech_tv")],
        [InlineKeyboardButton(text="🔧 Другое", callback_data="tech_other")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_services")]
    ])
    await callback.message.answer("Выберите тип технической проблемы:", reply_markup=keyboard)

@router.callback_query(F.data == "tech_ac")
async def tech_ac(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Спасибо! Информация передана в Техническую службу"
    await ask_for_comment(callback.message, state, response_text, "technical_ac")

@router.callback_query(F.data == "tech_wifi")
async def tech_wifi(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Спасибо! Информация передана в IT-службу"
    await ask_for_comment(callback.message, state, response_text, "technical_wifi")

@router.callback_query(F.data == "tech_tv")
async def tech_tv(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Спасибо! Информация передана в Техническую службу"
    await ask_for_comment(callback.message, state, response_text, "technical_tv")

@router.callback_query(F.data == "tech_other")
async def tech_other(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserAppeal.waiting_custom_problem)
    await callback.message.answer("Опишите проблему:")

@router.callback_query(F.data == "service_restaurant")
async def service_restaurant(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Меню рум-сервис", callback_data="menu_room_service")],
        [InlineKeyboardButton(text="🍽 Меню ресторана", callback_data="menu_restaurant")],
        [InlineKeyboardButton(text="📞 Соедините с рестораном", callback_data="connect_restaurant")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_services")]
    ])
    await callback.message.answer("Выберите услугу ресторана:", reply_markup=keyboard)

@router.callback_query(F.data == "menu_room_service")
async def menu_room_service(callback: CallbackQuery):
    await callback.answer()
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(current_dir, '..', 'menus', 'room_service_menu.pdf')
        menu_path = os.path.abspath(menu_path)
        
        if os.path.exists(menu_path):
            menu_file = FSInputFile(menu_path)
            await callback.message.answer_document(menu_file, caption="📋 Меню рум-сервис")
        else:
            await callback.message.answer("📋 Меню рум-сервис временно недоступно. Обратитесь к администратору.")
    except Exception:
        await callback.message.answer("📋 Меню рум-сервис временно недоступно. Обратитесь к администратору.")

@router.callback_query(F.data == "menu_restaurant")
async def menu_restaurant(callback: CallbackQuery):
    await callback.answer()
    try:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_path = os.path.join(current_dir, '..', 'menus', 'restaurant_menu.pdf')
        menu_path = os.path.abspath(menu_path)
        
        if os.path.exists(menu_path):
            menu_file = FSInputFile(menu_path)
            await callback.message.answer_document(menu_file, caption="🍽 Меню ресторана")
        else:
            await callback.message.answer("🍽 Меню ресторана временно недоступно. Обратитесь к администратору.")
    except Exception:
        await callback.message.answer("🍽 Меню ресторана временно недоступно. Обратитесь к администратору.")

@router.callback_query(F.data == "connect_restaurant")
async def connect_restaurant(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    response_text = "Мы перезвоним вам в ближайшее время"
    await ask_for_comment(callback.message, state, response_text, "restaurant_call")

@router.callback_query(F.data == "service_other")
async def service_other(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(UserAppeal.waiting_custom_problem)
    await callback.message.answer("Задайте вопрос:")

@router.callback_query(F.data == "back_services")
async def back_services(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_service_menu(callback.message, state)

@router.callback_query(F.data == "new_request")
async def new_request(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await show_service_menu(callback.message, state)


@router.message(UserAppeal.waiting_comment)
async def handle_comment(message: Message, state: FSMContext):
    comment = message.text.strip()
    data = await state.get_data()
    service_text = data.get("service_text", "")
    service_type = data.get("service_type", "other")

    await process_service_request(message, state, comment)

    if comment:
        await add_message(data.get("last_appeal_id"), "user", f"Комментарий: {comment}")
        await message.answer("✅ Комментарий добавлен к вашей заявке!")

@router.message(UserAppeal.waiting_custom_problem)
async def handle_custom_problem(message: Message, state: FSMContext):
    problem_text = message.text.strip()
    await state.update_data(service_text=problem_text, service_type="custom")
    await process_service_request(message, state, None)

async def process_service_request(message: Message, state: FSMContext, comment: str = None):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    data = await state.get_data()
    room = data.get("room", "не указан")
    service_text = data.get("service_text", "")
    service_type = data.get("service_type", "other")

    appeal_id = await create_service_request(user_id, username, room, service_type, service_text, comment)

    await state.update_data(last_appeal_id=appeal_id)

    await message.answer("✅ Ваша заявка отправлена!")
    await show_service_menu(message, state)


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
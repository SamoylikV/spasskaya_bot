import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.db import (
    get_appeals, get_appeal_with_messages, update_status, add_message,
    add_admin, remove_admin, is_admin, get_all_admins, get_appeals_stats,
    assign_appeal_to_admin, bulk_update_status
)
from config import ADMIN_ID

logger = logging.getLogger(__name__)

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_reply = State()
    waiting_search = State()
    waiting_room_filter = State()
    waiting_add_admin = State()
    waiting_mass_message = State()
    selecting_appeals = State()

pagination_states = {}

def create_pagination_keyboard(page, total_pages, prefix="appeals", **filters):
    keyboard = []
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Пред", callback_data=f"{prefix}_page:{page-1}"))
    
    nav_buttons.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="След ➡️", callback_data=f"{prefix}_page:{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    control_buttons = [
        InlineKeyboardButton(text="🔍 Поиск", callback_data="admin_search"),
        InlineKeyboardButton(text="🏠 Фильтр по комнате", callback_data="admin_room_filter"),
    ]
    keyboard.append(control_buttons)
    
    keyboard.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def create_appeal_keyboard(appeal_id, is_detailed=False):
    keyboard = []
    
    if not is_detailed:
        keyboard.append([
            InlineKeyboardButton(text="👁 Детально", callback_data=f"appeal_detail:{appeal_id}")
        ])
    
    action_buttons = [
        InlineKeyboardButton(text="✅ Получено", callback_data=f"admin_status:{appeal_id}:received"),
        InlineKeyboardButton(text="❌ Отказано", callback_data=f"admin_status:{appeal_id}:declined"),
    ]
    keyboard.append(action_buttons)
    
    second_row = [
        InlineKeyboardButton(text="✔ Выполнено", callback_data=f"admin_status:{appeal_id}:done"),
        InlineKeyboardButton(text="✉ Ответить", callback_data=f"admin_reply:{appeal_id}")
    ]
    keyboard.append(second_row)
    
    keyboard.append([
        InlineKeyboardButton(text="👤 Назначить админа", callback_data=f"assign_admin:{appeal_id}")
    ])
    
    if is_detailed:
        keyboard.append([
            InlineKeyboardButton(text="⬅️ К списку", callback_data="admin_open")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_appeal_message(appeal, is_detailed=False):
    status_emoji = {
        'new': '🆕',
        'received': '✅',
        'declined': '❌',
        'done': '✅'
    }
    
    created = appeal["created_at"]
    created_str = created.strftime("%d.%m.%Y %H:%M") if isinstance(created, datetime) else str(created)
    
    priority_emoji = "🔥" if appeal.get('priority', 1) > 1 else ""
    
    message = f"{priority_emoji}📨 **ID: {appeal['id']}** | {status_emoji.get(appeal['status'], '❓')} {appeal['status'].upper()}\n"
    message += f"👤 @{appeal['username']} | 🏠 Комната: {appeal['room']}\n"
    message += f"📅 {created_str}\n\n"
    
    if is_detailed:
        message += f"📝 **Текст обращения:**\n{appeal['text']}\n"
        if appeal.get('assigned_admin'):
            message += f"\n👤 Назначен админ: {appeal['assigned_admin']}"
    else:
        text = appeal['text'][:100] + "..." if len(appeal['text']) > 100 else appeal['text']
        message += f"📝 {text}"
    
    return message

@admin_router.message(Command("admin"))
async def admin_main_menu(message: Message):
    if not await is_admin(message.from_user.id) and message.from_user.id != ADMIN_ID:
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Все обращения", callback_data="admin_all_paged"),
            InlineKeyboardButton(text="🆕 Новые", callback_data="admin_new_paged")
        ],
        [
            InlineKeyboardButton(text="✅ В работе", callback_data="admin_received_paged"),
            InlineKeyboardButton(text="✔ Закрытые", callback_data="admin_done_paged")
        ],
        [
            InlineKeyboardButton(text="📊 Детальная статистика", callback_data="admin_detailed_stats"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="admin_search")
        ],
        [
            InlineKeyboardButton(text="👥 Управление админами", callback_data="admin_manage_admins"),
            InlineKeyboardButton(text="📢 Массовые операции", callback_data="admin_mass_ops")
        ]
    ])
    
    await message.answer(
        "🔧 **Административная панель**\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_main")
async def back_to_admin_main(callback: CallbackQuery):
    await callback.answer()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📂 Все обращения", callback_data="admin_all_paged"),
            InlineKeyboardButton(text="🆕 Новые", callback_data="admin_new_paged")
        ],
        [
            InlineKeyboardButton(text="✅ В работе", callback_data="admin_received_paged"),
            InlineKeyboardButton(text="✔ Закрытые", callback_data="admin_done_paged")
        ],
        [
            InlineKeyboardButton(text="📊 Детальная статистика", callback_data="admin_detailed_stats"),
            InlineKeyboardButton(text="🔍 Поиск", callback_data="admin_search")
        ],
        [
            InlineKeyboardButton(text="👥 Управление админами", callback_data="admin_manage_admins"),
            InlineKeyboardButton(text="📢 Массовые операции", callback_data="admin_mass_ops")
        ]
    ])
    
    await callback.message.edit_text(
        "🔧 **Административная панель**\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data.in_(["admin_all_paged", "admin_new_paged", "admin_received_paged", "admin_done_paged"]))
async def show_appeals_paged(callback: CallbackQuery):
    await callback.answer()
    
    status_map = {
        "admin_all_paged": None,
        "admin_new_paged": "new", 
        "admin_received_paged": "received",
        "admin_done_paged": "done"
    }
    
    status = status_map[callback.data]
    page = 1
    limit = 5 
    
    pagination_states[callback.from_user.id] = {
        'status': status,
        'page': page,
        'limit': limit
    }
    
    appeals, total_count = await get_appeals(status=status, limit=limit, offset=(page-1)*limit)
    total_pages = (total_count + limit - 1) // limit
    
    if not appeals:
        await callback.message.edit_text("📂 Обращений нет.")
        return
    
    await callback.message.edit_text(
        f"📂 **Обращения** (стр. {page}/{total_pages}, всего: {total_count})",
        parse_mode="Markdown"
    )
    
    for appeal in appeals:
        appeal_text = format_appeal_message(appeal)
        keyboard = create_appeal_keyboard(appeal['id'])
        
        await callback.message.answer(
            appeal_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    nav_keyboard = create_pagination_keyboard(page, total_pages)
    await callback.message.answer(
        "🔄 **Навигация:**",
        reply_markup=nav_keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data.startswith("appeals_page:"))
async def handle_pagination(callback: CallbackQuery):
    await callback.answer()
    
    page = int(callback.data.split(":")[1])
    user_state = pagination_states.get(callback.from_user.id, {})
    
    status = user_state.get('status')
    limit = user_state.get('limit', 5)
    
    appeals, total_count = await get_appeals(status=status, limit=limit, offset=(page-1)*limit)
    total_pages = (total_count + limit - 1) // limit
    
    pagination_states[callback.from_user.id]['page'] = page
    
    await callback.message.edit_text(
        f"📂 **Обращения** (стр. {page}/{total_pages}, всего: {total_count})",
        parse_mode="Markdown"
    )
    
    for appeal in appeals:
        appeal_text = format_appeal_message(appeal)
        keyboard = create_appeal_keyboard(appeal['id'])
        
        await callback.message.answer(
            appeal_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    nav_keyboard = create_pagination_keyboard(page, total_pages)
    await callback.message.answer(
        "🔄 **Навигация:**",
        reply_markup=nav_keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data.startswith("appeal_detail:"))
async def show_appeal_detail(callback: CallbackQuery):
    await callback.answer()
    
    appeal_id = int(callback.data.split(":")[1])
    appeal, messages = await get_appeal_with_messages(appeal_id)
    
    if not appeal:
        await callback.answer("Обращение не найдено", show_alert=True)
        return
    
    message_text = format_appeal_message(appeal, is_detailed=True) + "\n\n"
    
    if messages:
        message_text += "💬 **История сообщений:**\n\n"
        for msg in messages:
            sender_emoji = "👤" if msg['sender'] == 'user' else "👨‍💼"
            created = msg['created_at'].strftime("%d.%m.%Y %H:%M") if isinstance(msg['created_at'], datetime) else str(msg['created_at'])
            message_text += f"{sender_emoji} **{msg['sender'].title()}** ({created}):\n{msg['text']}\n\n"
    
    keyboard = create_appeal_keyboard(appeal_id, is_detailed=True)
    
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_detailed_stats")
async def show_detailed_stats(callback: CallbackQuery):
    await callback.answer()
    
    stats = await get_appeals_stats()
    
    message_text = "📊 **Детальная статистика**\n\n"
    message_text += f"📂 Всего обращений: **{stats['total']}**\n"
    message_text += f"🆕 Новых: **{stats['new']}**\n" 
    message_text += f"✅ В работе: **{stats['received']}**\n"
    message_text += f"✔ Выполненных: **{stats['done']}**\n"
    message_text += f"❌ Отклонённых: **{stats['declined']}**\n\n"
    
    if stats['daily']:
        message_text += "📈 **Статистика по дням (последние 7 дней):**\n"
        for day_stat in stats['daily']:
            date = day_stat['date'].strftime("%d.%m") if isinstance(day_stat['date'], datetime) else str(day_stat['date'])
            message_text += f"📅 {date}: {day_stat['count']} обращений\n"
        message_text += "\n"
    
    if stats['rooms']:
        message_text += "🏠 **Топ-10 комнат по обращениям:**\n"
        for i, room_stat in enumerate(stats['rooms'], 1):
            message_text += f"{i}. Комната {room_stat['room']}: {room_stat['count']} обращений\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_manage_admins")
async def manage_admins_menu(callback: CallbackQuery):
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только главный админ может управлять администраторами", show_alert=True)
        return
    
    admins = await get_all_admins()
    
    message_text = "👥 **Управление администраторами**\n\n"
    
    if admins:
        message_text += "📋 **Список админов:**\n"
        for admin in admins:
            message_text += f"• @{admin['username']} (ID: {admin['user_id']}) - {admin['role']}\n"
        message_text += "\n"
    else:
        message_text += "📋 Дополнительных админов нет.\n\n"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить админа", callback_data="admin_add_admin")],
        [InlineKeyboardButton(text="➖ Удалить админа", callback_data="admin_remove_admin")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(
        message_text,
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_search")
async def start_search(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_search)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(
        "🔍 **Поиск по обращениям**\n\nВведите текст для поиска (будет искать в тексте обращений и именах пользователей):",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.message(AdminStates.waiting_search)
async def process_search(message: Message, state: FSMContext):
    search_query = message.text.strip()
    await state.clear()
    
    appeals, total_count = await get_appeals(search_query=search_query, limit=10)
    
    if not appeals:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        await message.answer(
            f"🔍 По запросу '{search_query}' ничего не найдено.",
            reply_markup=keyboard
        )
        return
    
    await message.answer(
        f"🔍 **Результаты поиска** по запросу '{search_query}'\nНайдено: {total_count} обращений",
        parse_mode="Markdown"
    )
    
    for appeal in appeals:
        appeal_text = format_appeal_message(appeal)
        keyboard = create_appeal_keyboard(appeal['id'])
        
        await message.answer(
            appeal_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    nav_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
    ])
    
    await message.answer(
        "🔄 **Меню:**",
        reply_markup=nav_keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_room_filter")
async def start_room_filter(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(AdminStates.waiting_room_filter)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(
        "🏠 **Фильтр по комнате**\n\nВведите номер комнаты:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.message(AdminStates.waiting_room_filter)
async def process_room_filter(message: Message, state: FSMContext):
    room = message.text.strip()
    await state.clear()
    
    appeals, total_count = await get_appeals(room=room, limit=10)
    
    if not appeals:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        await message.answer(
            f"🏠 Обращений из комнаты '{room}' не найдено.",
            reply_markup=keyboard
        )
        return
    
    await message.answer(
        f"🏠 **Обращения из комнаты {room}**\nНайдено: {total_count} обращений",
        parse_mode="Markdown"
    )
    
    for appeal in appeals:
        appeal_text = format_appeal_message(appeal)
        keyboard = create_appeal_keyboard(appeal['id'])
        
        await message.answer(
            appeal_text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    
    nav_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
    ])
    
    await message.answer(
        "🔄 **Меню:**",
        reply_markup=nav_keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data == "admin_add_admin")
async def start_add_admin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Только главный админ может добавлять администраторов", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_add_admin)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_manage_admins")]
    ])
    
    await callback.message.edit_text(
        "➕ **Добавление администратора**\n\nПеришлите сообщение от пользователя или введите его ID:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.message(AdminStates.waiting_add_admin)
async def process_add_admin(message: Message, state: FSMContext):
    await state.clear()
    
    user_id = None
    username = None
    
    if message.forward_from:
        user_id = message.forward_from.id
        username = message.forward_from.username or str(user_id)
    elif message.text and message.text.isdigit():
        user_id = int(message.text)
        username = str(user_id)
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        await message.answer(
            "❌ Неверный формат. Перешлите сообщение от пользователя или введите его ID.",
            reply_markup=keyboard
        )
        return
    
    try:
        await add_admin(user_id, username)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Управление админами", callback_data="admin_manage_admins")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        await message.answer(
            f"✅ Пользователь @{username} (ID: {user_id}) добавлен в администраторы.",
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Ошибка добавления админа: {e}")
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        await message.answer(
            "❌ Ошибка при добавлении администратора.",
            reply_markup=keyboard
        )

@admin_router.callback_query(F.data == "admin_mass_ops")
async def mass_operations_menu(callback: CallbackQuery):
    await callback.answer()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Массово выполнить", callback_data="mass_done")],
        [InlineKeyboardButton(text="❌ Массово отклонить", callback_data="mass_declined")],
        [InlineKeyboardButton(text="📢 Массовая рассылка", callback_data="mass_broadcast")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
    ])
    
    await callback.message.edit_text(
        "📢 **Массовые операции**\n\nВыберите действие:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.callback_query(F.data.startswith("admin_status:"))
async def admin_set_status(callback: CallbackQuery):
    await callback.answer()
    
    try:
        _, appeal_id, status = callback.data.split(":")
        appeal_id = int(appeal_id)
    except ValueError:
        await callback.answer("Неправильный формат команды.", show_alert=True)
        return
    
    try:
        user_id = await update_status(appeal_id, status)
        if user_id:
            from aiogram import Bot
            from config import TOKEN
            bot = Bot(TOKEN)
            
            status_messages = {
                'received': 'получено в работу ✅',
                'declined': 'отклонено ❌',
                'done': 'выполнено ✅'
            }
            
            status_msg = status_messages.get(status, f"изменён на {status}")
            
            if status == "done":
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❗ Вопрос не решили", callback_data=f"user_reopen:{appeal_id}")]
                ])
                await bot.send_message(
                    user_id, 
                    f"📬 Ваше обращение #{appeal_id} {status_msg}", 
                    reply_markup=keyboard
                )
            else:
                await bot.send_message(
                    user_id, 
                    f"📬 Статус вашего обращения #{appeal_id} {status_msg}"
                )
        
        await callback.message.answer(f"✅ Статус обращения {appeal_id} изменён на '{status}'.")
        
    except Exception as e:
        logger.error(f"Ошибка изменения статуса: {e}")
        await callback.answer("Ошибка при изменении статуса.", show_alert=True)

@admin_router.callback_query(F.data.startswith("admin_reply:"))
async def start_admin_reply(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    
    try:
        _, appeal_id = callback.data.split(":")
        appeal_id = int(appeal_id)
    except Exception:
        await callback.answer("Неправильный ID обращения.", show_alert=True)
        return
    
    await state.update_data(appeal_id=appeal_id)
    await state.set_state(AdminStates.waiting_reply)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_main")]
    ])
    
    await callback.message.answer(
        f"✉️ **Ответ на обращение #{appeal_id}**\n\nВведите текст ответа:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@admin_router.message(AdminStates.waiting_reply)
async def send_admin_reply(message: Message, state: FSMContext):
    data = await state.get_data()
    appeal_id = data.get("appeal_id")
    
    if not appeal_id:
        await message.answer("❌ ID обращения не найден. Попробуйте ещё раз через /admin.")
        await state.clear()
        return
    
    try:
        appeal, _ = await get_appeal_with_messages(appeal_id)
        
        if not appeal:
            await message.answer("❌ Обращение не найдено.")
            await state.clear()
            return
        
        user_id = appeal["user_id"]
        
        from aiogram import Bot
        from config import TOKEN
        bot = Bot(TOKEN)
        await bot.send_message(
            user_id, 
            f"📢 **Ответ администратора на обращение #{appeal_id}:**\n\n{message.text}"
        )
        
        await add_message(appeal_id, "admin", message.text)
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="admin_main")]
        ])
        
        await message.answer(
            "✅ Сообщение отправлено пользователю.",
            reply_markup=keyboard
        )
        
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")
        await message.answer("❌ Ошибка при отправке сообщения.")
    
    await state.clear()

@admin_router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery):
    await callback.answer()

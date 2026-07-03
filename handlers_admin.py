import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import config
import storage

admin_router = Router()

class AdminStates(StatesGroup):
    waiting_for_mailing_text = State()
    waiting_for_bot_username = State()  # Состояние ожидания юзернейма для добавления
    waiting_for_bot_del = State()       # Состояние ожидания юзернейма для удаления

def get_admin_main_kb() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="📊 Статистика бота", callback_data="adm:stats", style="primary"),
            InlineKeyboardButton(text="📢 Запустить рассылку", callback_data="adm:mailing", style="primary")
        ],
        [
            InlineKeyboardButton(text="⚙️ Статус логирования", callback_data="adm:logs_menu", style="primary"),
            InlineKeyboardButton(text="🔒 Список мутов", callback_data="adm:muted_list", style="primary")
        ],
        [
            InlineKeyboardButton(text="🤖 Верификация ботов", callback_data="adm:verified_menu", style="primary")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_back_kb(target: str = "adm:main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=target)]
    ])

@admin_router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in config.ADMIN_IDS:
        return
        
    await message.answer(
        "🛠 <b>Центральная панель управления Business Monitor</b>\n"
        "Выберите необходимый инструмент управления ниже:", 
        reply_markup=get_admin_main_kb(), 
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "adm:main")
async def back_to_admin_main(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS: return
    await state.clear()
    await callback.message.edit_text(
        "🛠 <b>Центральная панель управления Business Monitor</b>\n"
        "Выберите необходимый инструмент управления ниже:",
        reply_markup=get_admin_main_kb(),
        parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data == "adm:stats")
async def show_global_stats(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    
    user_stats_dict = getattr(storage, "user_stats", {})
    total_users = len(user_stats_dict)
    
    total_cached = sum(u.get("total_cached", 0) for u in user_stats_dict.values())
    total_edited = sum(u.get("total_edited", 0) for u in user_stats_dict.values())
    total_deleted = sum(u.get("total_deleted", 0) for u in user_stats_dict.values())
    
    stats_text = (
        f"📊 <b>Глобальная статистика системы</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Всего клиентов в базе: <code>{total_users}</code>\n"
        f"📥 Индексировано сообщений: <code>{total_cached}</code>\n"
        f"✏️ Перехвачено изменений: <code>{total_edited}</code>\n"
        f"🗑 Поймано удалений: <code>{total_deleted}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━"
    )
    await callback.message.edit_text(stats_text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "adm:logs_menu")
async def show_logs_management(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    if not hasattr(storage, "LOGS_ACTIVE"): storage.LOGS_ACTIVE = True
        
    status = "🟢 АКТИВЕН" if storage.LOGS_ACTIVE else "🔴 ВЫКЛЮЧЕН"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Включить логи", callback_data="adm_logs:on", style="success"),
            InlineKeyboardButton(text="🔴 Выключить логи", callback_data="adm_logs:off", style="danger")
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="adm:main")]
    ])
    await callback.message.edit_text(
        f"⚙️ <b>Управление глобальным логгером</b>\n\nТекущее состояние: <b>{status}</b>", 
        reply_markup=kb, parse_mode="HTML"
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("adm_logs:"))
async def toggle_logs(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    action = callback.data.split(":")[1]
    storage.LOGS_ACTIVE = (action == "on")
    await show_logs_management(callback)
    await callback.answer("Статус изменен")

@admin_router.callback_query(F.data == "adm:muted_list")
async def show_muted_users(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    muted_set = getattr(storage, "muted_users", set())
    
    if not muted_set:
        text = "🔒 <b>Список мутов</b>\n\nАктивных мутов нет."
    else:
        lines = [f"• <code>{uid}</code>" for uid in muted_set]
        text = "🔒 <b>Список замученных пользователей:</b>\n\n" + "\n".join(lines)
        
    await callback.message.edit_text(text, reply_markup=get_back_kb(), parse_mode="HTML")
    await callback.answer()

# МЕНЮ УПРАВЛЕНИЯ ВЕРИФИЦИРОВАННЫМИ БОТАМИ
@admin_router.callback_query(F.data == "adm:verified_menu")
async def show_verified_bots_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS: return
    await state.clear()
    
    if not hasattr(storage, "verified_bots"): 
        storage.verified_bots = set()
        
    bots_list = sorted(list(storage.verified_bots))
    if not bots_list:
        bots_text = "<i>Список верифицированных ботов пуст.</i>"
    else:
        bots_text = "\n".join([f"• <code>@{b}</code>" for b in bots_list])
        
    text = (
        f"🤖 <b>Белый список верифицированных ботов</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{bots_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Выберите действие:"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Добавить", callback_data="adm_bot:add", style="success"),
            InlineKeyboardButton(text="➖ Удалить", callback_data="adm_bot:del", style="danger")
        ],
        [InlineKeyboardButton(text="⬅️ В админку", callback_data="adm:main")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()

@admin_router.callback_query(F.data == "adm_bot:add")
async def add_verified_bot_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_bot_username)
    await callback.message.edit_text(
        "➕ <b>Добавление бота в белый список</b>\n\n"
        "Отправьте юзернейм бота (например, <code>@sample_bot</code> или просто <code>sample_bot</code>):",
        reply_markup=get_back_kb("adm:verified_menu"), parse_mode="HTML"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_bot_username)
async def process_add_verified_bot(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    raw_text = message.text.strip().replace("@", "").lower()
    
    if not raw_text.endswith("bot"):
        await message.answer(
            "❌ <b>Ошибка:</b> Юзернейм должен заканчиваться на <code>bot</code>.\n"
            "Попробуйте еще раз или вернитесь назад:", 
            reply_markup=get_back_kb("adm:verified_menu"), 
            parse_mode="HTML"
        )
        return
        
    if not hasattr(storage, "verified_bots"): storage.verified_bots = set()
    if not hasattr(storage, "seen_bots"): storage.seen_bots = set()
    
    storage.verified_bots.add(raw_text)
    storage.seen_bots.discard(raw_text)  # Сбрасываем кэш, чтобы триггернуть проверку заново
    
    await state.clear()
    await message.answer(
        f"✅ Бот <code>@{raw_text}</code> успешно добавлен в белый список и верифицирован!",
        reply_markup=get_back_kb("adm:verified_menu"),
        parse_mode="HTML"
    )

@admin_router.callback_query(F.data == "adm_bot:del")
async def del_verified_bot_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_bot_del)
    await callback.message.edit_text(
        "➖ <b>Удаление бота из белого списка</b>\n\n"
        "Отправьте юзернейм бота, которого нужно убрать из верифицированных:",
        reply_markup=get_back_kb("adm:verified_menu"), parse_mode="HTML"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_bot_del)
async def process_del_verified_bot(message: Message, state: FSMContext):
    if message.from_user.id not in config.ADMIN_IDS: return
    
    raw_text = message.text.strip().replace("@", "").lower()
    if not hasattr(storage, "verified_bots"): storage.verified_bots = set()
    
    if raw_text in storage.verified_bots:
        storage.verified_bots.discard(raw_text)
        if hasattr(storage, "seen_bots"):
            storage.seen_bots.discard(raw_text)
        text = f"✅ Бот <code>@{raw_text}</code> успешно удален из белого списка."
    else:
        text = f"❌ Бот <code>@{raw_text}</code> не найден в белом списке."
        
    await state.clear()
    await message.answer(text, reply_markup=get_back_kb("adm:verified_menu"), parse_mode="HTML")

# РАССЫЛКА
@admin_router.callback_query(F.data == "adm:mailing")
async def start_mailing_process(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in config.ADMIN_IDS: return
    await state.set_state(AdminStates.waiting_for_mailing_text)
    await callback.message.edit_text(
        "📢 <b>Режим создания рассылки</b>\n\nОтправьте текст сообщения для пользователей.",
        reply_markup=get_back_kb(), parse_mode="HTML"
    )
    await callback.answer()

@admin_router.message(AdminStates.waiting_for_mailing_text)
async def process_mailing_delivery(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id not in config.ADMIN_IDS: return
    mailing_text = message.text
    await state.clear()
    
    user_stats_dict = getattr(storage, "user_stats", {})
    target_users = list(user_stats_dict.keys())
    
    if not target_users:
        await message.answer("❌ База пользователей пуста.", reply_markup=get_back_kb())
        return
        
    status_msg = await message.answer(f"⏳ Рассылка запущена... Целей: {len(target_users)}")
    success_count, failed_count = 0, 0
    
    for user_id in target_users:
        try:
            await bot.send_message(chat_id=user_id, text=mailing_text, parse_mode="HTML")
            success_count += 1
            await asyncio.sleep(0.05) 
        except Exception:
            failed_count += 1
            
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n📥 Доставлено: <code>{success_count}</code>\n❌ Ошибки: <code>{failed_count}</code>",
        reply_markup=get_back_kb(), parse_mode="HTML"
    )

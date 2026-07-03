from aiogram import Router, F, Bot, BaseMiddleware
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, TelegramObject
from aiogram.filters import Command
from typing import Callable, Dict, Any, Awaitable
import config
import storage

menu_router = Router()

# Инициализация многопользовательских структур в ОЗУ
if not hasattr(storage, "user_logs_active"): storage.user_logs_active = {}
if not hasattr(storage, "user_stats"): storage.user_stats = {}

# --- Система проверки обязательной подписки ---

async def check_subscription(bot: Bot, user_id: int) -> bool:
    """Проверяет, подписан ли пользователь на обязательный канал"""
    try:
        member = await bot.get_chat_member(chat_id="@ghostextra", user_id=user_id)
        return member.status in ["creator", "administrator", "member"]
    except Exception:
        return False

class SubCheckMiddleware(BaseMiddleware):
    """Автоматический страж: блокирует доступ, если юзер отписался"""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        bot: Bot = data.get("bot")
        user = data.get("event_from_user")
        
        if not user or not bot:
            return await handler(event, data)
            
        # Пропускаем базовый /start и кнопку проверки, чтобы избежать мертвой петли
        if isinstance(event, Message) and event.text == "/start":
            return await handler(event, data)
        if isinstance(event, CallbackQuery) and event.data == "sub:check":
            return await handler(event, data)
            
        # Если пользователь отписался во время работы с меню
        if not await check_subscription(bot, user.id):
            if isinstance(event, CallbackQuery):
                await event.answer(
                    "⚠️ Доступ приостановлен!\n\nВы отписались от канала @ghostextra. Работа всех бизнес-функций и логгера заморожена до восстановления подписки.", 
                    show_alert=True
                )
            elif isinstance(event, Message):
                await event.answer(
                    "⚠️ Функции заблокированы!\nДля использования функций трекера подпишитесь на канал: https://t.me/ghostextra"
                )
            return
            
        return await handler(event, data)

# Подключаем автоматическую проверку ко всем хендлерам роутера
menu_router.message.outer_middleware(SubCheckMiddleware())
menu_router.callback_query.outer_middleware(SubCheckMiddleware())

# --- Клавиатуры ---

def get_main_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="Профиль", callback_data="menu:profile"),
            InlineKeyboardButton(text="Статистика", callback_data="menu:stats")
        ],
        [
            InlineKeyboardButton(text="Изменённые", callback_data="menu:edited"),
            InlineKeyboardButton(text="Удалённые", callback_data="menu:deleted")
        ],
        [
            InlineKeyboardButton(text="Настройки", callback_data="menu:settings"),
            InlineKeyboardButton(text="Помощь", callback_data="menu:help")
        ]
    ]
    if user_id in config.ADMIN_IDS:
        buttons.append([InlineKeyboardButton(text="Глобальный Мониторинг", callback_data="admin:panel")])
        
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# --- Хендлеры подписки и старта ---

@menu_router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    u_id = message.from_user.id
    if u_id not in storage.user_stats:
        storage.user_stats[u_id] = {"total_cached": 0, "total_edited": 0, "total_deleted": 0}
    if u_id not in storage.user_logs_active:
        storage.user_logs_active[u_id] = True

    # Проверяем подписку прямо на старте
    if not await check_subscription(bot, u_id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Подписаться", url="https://t.me/ghostextra")],
            [InlineKeyboardButton(text="✅ Проверить", callback_data="sub:check")]
        ])
        await message.answer_photo(
            photo="https://t.me/claudmudila/129354",
            caption="Для продолжения подпишитесь на наш информационный канал.",
            reply_markup=kb
        )
        return

    # Если уже подписан — сразу выдаем меню без текста
    await message.answer_photo(
        photo="https://t.me/claudmudila/129354",
        reply_markup=get_main_menu_keyboard(u_id)
    )

@menu_router.callback_query(F.data == "sub:check")
async def process_sub_check(callback: CallbackQuery, bot: Bot):
    u_id = callback.from_user.id
    
    if await check_subscription(bot, u_id):
        # Если подписался — удаляем плашку с подпиской
        try:
            await callback.message.delete()
        except Exception:
            pass
            
        # Отправляем чистое главное меню
        await callback.message.answer_photo(
            photo="https://t.me/claudmudila/129354",
            reply_markup=get_main_menu_keyboard(u_id)
        )
        await callback.answer("Успешно! Доступ к системе открыт.", show_alert=False)
    else:
        # Если всё ещё не подписан
        await callback.answer("❌ Вы всё ещё не подписались на канал @ghostextra!", show_alert=True)


# --- Оригинальный код меню ---

@menu_router.callback_query(F.data == "menu:profile")
async def check_profile(callback: CallbackQuery):
    u_id = callback.from_user.id
    is_admin = u_id in config.ADMIN_IDS
    status = "Активен (Администратор)" if is_admin else "Активен (Публичный доступ)"
    
    text = (
        f"Ваш профиль в системе\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"ID: <code>{u_id}</code>\n"
        f"Статус: {status}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Бот успешно изолирует ваши данные. Другие пользователи не имеют доступа к вашим логам."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")

@menu_router.callback_query(F.data == "menu:stats")
async def check_stats(callback: CallbackQuery):
    u_id = callback.from_user.id
    u_stats = storage.user_stats.get(u_id, {"total_cached": 0, "total_edited": 0, "total_deleted": 0})
    
    text = (
        f"Ваша личная статистика\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"Индексировано сообщений: {u_stats['total_cached']}\n"
        f"Зафиксировано изменений: {u_stats['total_edited']}\n"
        f"Поймано удалений: {u_stats['total_deleted']}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")

@menu_router.callback_query(F.data == "menu:edited")
async def check_edited(callback: CallbackQuery):
    text = "Лог изменений сообщений. Мониторинг происходит в реальном времени внутри ваших бизнес-чатов."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb)

@menu_router.callback_query(F.data == "menu:deleted")
async def check_deleted(callback: CallbackQuery):
    text = "Лог удалений сообщений. При фиксации удаления бот мгновенно отправит вам срез истории в ЛС."
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb)

@menu_router.callback_query(F.data == "menu:settings")
async def check_settings(callback: CallbackQuery):
    u_id = callback.from_user.id
    is_active = storage.user_logs_active.get(u_id, True)
    status = "ВКЛ" if is_active else "ВЫКЛ"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Включить", callback_data="set_logs:on"),
            InlineKeyboardButton(text="Выключить", callback_data="set_logs:off")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="menu:back")]
    ])
    await callback.message.edit_caption(caption=f"Персональные настройки\n\nСтатус вашего перехватчика событий: {status}", reply_markup=kb)

@menu_router.callback_query(F.data.startswith("set_logs:"))
async def toggle_settings(callback: CallbackQuery):
    u_id = callback.from_user.id
    action = callback.data.split(":")[1]
    
    storage.user_logs_active[u_id] = (action == "on")
    is_active = storage.user_logs_active[u_id]
    status = "ВКЛ" if is_active else "ВЫКЛ"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Включить", callback_data="set_logs:on"),
            InlineKeyboardButton(text="Выключить", callback_data="set_logs:off")
        ],
        [InlineKeyboardButton(text="Назад", callback_data="menu:back")]
    ])
    await callback.message.edit_caption(caption=f"Персональные настройки\n\nСтатус вашего перехватчика событий: {status}", reply_markup=kb)
    await callback.answer("Ваши настройки успешно обновлены")

@menu_router.callback_query(F.data == "menu:help")
async def check_help(callback: CallbackQuery):
    text = (
        f"Инструкция по подключению\n\n"
        f"1. Откройте Настройки вашего Telegram -> Telegram Бизнес -> Чат-боты.\n"
        f"2. Вставьте юзернейм (@username) этого бота.\n"
        f"3. Выберите чаты, в которых бот должен работать (все или определенные).\n"
        f"4. Готово! Бот начнет присылать отчеты сюда в автоматическом режиме."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Назад", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb)

@menu_router.callback_query(F.data == "menu:back")
async def go_back(callback: CallbackQuery):
    await callback.message.edit_caption(
        caption="",
        reply_markup=get_main_menu_keyboard(callback.from_user.id)
    )

@menu_router.callback_query(F.data == "admin:panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in config.ADMIN_IDS: return
    
    total_clients = len(storage.user_logs_active)
    text = (
        f"📊 <b>Панель управления общедоступным ботом</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Режим работы: <code>Свободный доступ</code>\n"
        f"Всего уникальных клиентов в ОЗУ: <code>{total_clients}</code>\n\n"
        f"Бот полностью автономен и не требует ручной активации сессий."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="В меню", callback_data="menu:back")]])
    await callback.message.edit_caption(caption=text, reply_markup=kb, parse_mode="HTML")

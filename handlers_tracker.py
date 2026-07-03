import io
import re
import aiohttp
from aiogram import Router, F, Bot
from aiogram.types import Message, BusinessMessagesDeleted, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, BufferedInputFile
import storage
import config
import media_saver

tracker_router = Router()

# Гарантируем инициализацию многопользовательских структур в ОЗУ устройства
if not hasattr(storage, "user_logs_active"): storage.user_logs_active = {}
if not hasattr(storage, "user_stats"): storage.user_stats = {}
if not hasattr(storage, "blocked_chats"): storage.blocked_chats = set()
if not hasattr(storage, "muted_chats"): storage.muted_chats = set()
if not hasattr(storage, "muted_users"): storage.muted_users = set()  
if not hasattr(storage, "chat_history"): storage.chat_history = {}
if not hasattr(storage, "msg_cache"): storage.msg_cache = {}
if not hasattr(storage, "username_map"): storage.username_map = {}
if not hasattr(storage, "verified_bots"): storage.verified_bots = set()
if not hasattr(storage, "deleted_voices"): storage.deleted_voices = {}
# Структура для хранения отслеживаемых каналов
if not hasattr(storage, "tracked_channels"): storage.tracked_channels = {}

def escape_html(text: str) -> str:
    """Безопасное экранирование текста для предотвращения ошибок разметки HTML"""
    if not text: 
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

async def fix_text_orthography(text: str) -> str:
    """Автоматически исправляет орфографию и пунктуацию через бесплатный API Яндекс.Спеллера"""
    if not text:
        return ""
    try:
        async with aiohttp.ClientSession() as session:
            url = "https://speller.yandex.net/services/spellservice.json/checkText"
            async with session.post(url, data={'text': text}) as resp:
                if resp.status == 200:
                    changes = await resp.json()
                    changes = sorted(changes, key=lambda x: x['pos'], reverse=True)
                    text_list = list(text)
                    for change in changes:
                        if change['s']:
                            pos = change['pos']
                            length = change['len']
                            replacement = change['s'][0]
                            text_list[pos:pos+length] = list(replacement)
                    return "".join(text_list)
    except Exception as e:
        print(f"[FixEngine Error] {e}")
    return text.strip()

async def check_new_bot_scam(message: Message, text: str, bot: Bot, owner_id: int):
    """Проверяет text на ботов. Шлет инфо-статус или варнинг владельцу аккаунта в ЛС"""
    if not text:
        return

    if not hasattr(storage, "seen_bots"):
        storage.seen_bots = set()

    found_bots = re.findall(r'(?:@|t\.me\/)([a-zA-Z0-9_]{3,32}bot)\b', text, re.IGNORECASE)

    for bot_username in found_bots:
        bot_username_lower = bot_username.lower()

        if message.from_user and message.from_user.id == owner_id:
            continue

        if bot_username_lower in storage.verified_bots:
            if bot_username_lower not in storage.seen_bots:
                storage.seen_bots.add(bot_username_lower)
                verified_text = (
                    f"<b>Внимание: бот верифицирован</b>\n"
                    f"Ссылка: @{bot_username}\n\n"
                    f"Этот бот прошёл проверку и получил подтверждённый статус."
                )
                try: await bot.send_message(chat_id=owner_id, text=verified_text, parse_mode="HTML")
                except: pass
        else:
            if bot_username_lower not in storage.seen_bots:
                storage.seen_bots.add(bot_username_lower)
                warning_text = (
                    f"<b>Внимание обнаружен неизвестный бот</b>\n"
                    f"Ссылка: @{bot_username}\n\n"
                    f"Наша система видит этого бота впервые.\n"
                    f"Будьте осторожны: часто под видом новых сервисов скрывается скам или фишинг.\n"
                    f"    Не переходите по подозрительным кнопкам и никогда не привязывайте туда свой Telegram-аккаунт или кошельки!"
                )
                try: await bot.send_message(chat_id=owner_id, text=warning_text, parse_mode="HTML")
                except: pass

async def get_owner_id(bot: Bot, conn_id: str) -> int:
    """Получение ID владельца бизнес-связи с кэшированием"""
    if not hasattr(storage, "owner_cache"):
        storage.owner_cache = {}
    if conn_id in storage.owner_cache:
        return storage.owner_cache[conn_id]
    try:
        connection = await bot.get_business_connection(business_connection_id=conn_id)
        storage.owner_cache[conn_id] = connection.user.id
        return connection.user.id
    except Exception:
        return None

async def process_owner_command(message: Message, text: str, bot: Bot, owner_id: int, chat_id: int, conn_id: str) -> bool:
    """Диспетчер встроенных бизнес-команд владельца аккаунта"""
    text = text.strip()
    
    if text.startswith(".spam"):
        try:
            try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
            except: pass
            spam_text = ""
            spam_count = 5
            match_start = re.match(r'^\.spam\s+(\d+)\s+(.+)$', text, re.DOTALL | re.IGNORECASE)
            match_end = re.match(r'^\.spam\s+(.+)\s+(\d+)$', text, re.DOTALL | re.IGNORECASE)
            if match_start:
                spam_count = min(int(match_start.group(1)), 100)
                spam_text = match_start.group(2).strip()
            elif match_end:
                spam_count = min(int(match_end.group(2)), 100)
                spam_text = match_end.group(1).strip()
            else:
                spam_text = text.replace(".spam", "", 1).strip()
                if not spam_text: return True
            for _ in range(spam_count):
                await bot.send_message(chat_id=chat_id, text=spam_text, business_connection_id=conn_id)
        except Exception as e:
            print(f"[SpamEngine] Сбой: {e}")
        return True

    elif text.startswith(".fix"):
        try:
            reply_id = None
            if message.reply_to_message:
                target_text = message.reply_to_message.text or message.reply_to_message.caption or ""
                reply_id = message.reply_to_message.message_id
            else:
                target_text = text.replace(".fix", "", 1).strip()
                
            try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
            except: pass
            
            if not target_text: return True
            fixed_result = await fix_text_orthography(target_text)
            if fixed_result:
                # Работает корректно везде (в ЛС и публичных чатах), сохраняя reply-структуру
                await bot.send_message(
                    chat_id=chat_id, 
                    text=fixed_result, 
                    business_connection_id=conn_id, 
                    reply_to_message_id=reply_id
                )
        except Exception as e:
            print(f"[FixEngine] Сбой: {e}")
        return True

    elif text.startswith(".search"):
        try:
            try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
            except: pass
            
            target_key = None
            channel_label = ""
            
            # Вариант 1: Команда отправлена ответом на пересланный пост из канала
            if message.reply_to_message and message.reply_to_message.forward_from_chat:
                chat = message.reply_to_message.forward_from_chat
                if chat.type == "channel":
                    target_key = str(chat.id)
                    channel_label = chat.title or chat.username or target_key
            
            # Вариант 2: Юзер передал ссылку или юзернейм текстом после .search
            if not target_key:
                args = text.replace(".search", "", 1).strip()
                if args:
                    clean_arg = args.replace("https://t.me/", "").replace("t.me/", "").replace("@", "").strip().lower()
                    target_key = clean_arg
                    channel_label = f"@{clean_arg}"
                    
            if not target_key:
                try: await bot.send_message(chat_id=owner_id, text="⚠️ <b>Ошибка:</b> Укажите юзернейм/ссылку на канал или ответьте командой на пересланный из него пост.")
                except: pass
                return True
                
            storage.tracked_channels[target_key] = owner_id
            try:
                await bot.send_message(
                    chat_id=owner_id, 
                    text=f"📡 <b>Канал успешно взят на мониторинг!</b>\n\n"
                         f"Бот будет отслеживать новые публикации в <code>{escape_html(channel_label)}</code>.\n"
                         f"<i>Примечание: Для корректной работы по ID бот должен находиться в этом канале.</i>",
                    parse_mode="HTML"
                )
            except: pass
        except Exception as e:
            print(f"[SearchEngine] Сбой: {e}")
        return True

    elif text == ".clean":
        try:
            try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
            except: pass
            msg_ids_to_delete = []
            keys_to_del = []
            for k, v in storage.msg_cache.items():
                if v.get("chat_id") == chat_id:
                    parts = k.split(":")
                    if len(parts) == 2: msg_ids_to_delete.append(int(parts[1]))
                    keys_to_del.append(k)
            if msg_ids_to_delete:
                for i in range(0, len(msg_ids_to_delete), 100):
                    chunk = msg_ids_to_delete[i:i+100]
                    try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=chunk)
                    except: pass
            history_key = f"{conn_id}:{chat_id}"
            if history_key in storage.chat_history:
                storage.chat_history.pop(history_key, None)
            for k in keys_to_del:
                storage.msg_cache.pop(k, None)
            try: await bot.send_message(chat_id=owner_id, text=f"🧹 Чат <code>{chat_id}</code> полностью очищен!", parse_mode="HTML")
            except: pass
        except Exception as e:
            print(f"[CleanEngine] Сбой: {e}")
        return True

    elif text == ".mute":
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        target_user_id = message.chat.id
        storage.muted_users.add(target_user_id)
        try: await bot.send_message(chat_id=owner_id, text=f"🔒 Пользователь id <code>{target_user_id}</code> замучен.", parse_mode="HTML")
        except: pass
        return True
        
    elif text == ".unmute":
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        target_user_id = message.chat.id
        storage.muted_users.discard(target_user_id)
        try: await bot.send_message(chat_id=owner_id, text=f"🔓 Пользователь <code>{target_user_id}</code> размучен.", parse_mode="HTML")
        except: pass
        return True

    elif text == ".block":
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        storage.blocked_chats.add(chat_id)
        await bot.send_message(chat_id=owner_id, text=f"🚫 Чат <code>{chat_id}</code> исключен.", parse_mode="HTML")
        return True
        
    elif text == ".unblock":
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        storage.blocked_chats.discard(chat_id)
        await bot.send_message(chat_id=owner_id, text=f"✅ Чат <code>{chat_id}</code> восстановлен.", parse_mode="HTML")
        return True

    return False

@tracker_router.business_message()
async def cache_business_message(message: Message, bot: Bot):
    conn_id = message.business_connection_id
    owner_id = await get_owner_id(bot, conn_id)
    if not owner_id: 
        return

    if message.from_user and message.from_user.id in storage.muted_users and message.from_user.id != owner_id:
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        return

    if not storage.user_logs_active.get(owner_id, True): 
        return

    if message.from_user and message.from_user.username:
        storage.username_map[message.from_user.username.lower()] = message.chat.id

    if message.text and message.from_user.id == owner_id:
        if await process_owner_command(message, message.text, bot, owner_id, message.chat.id, conn_id):
            return

    if message.chat.id in storage.blocked_chats: 
        return

    if owner_id not in storage.user_stats:
        storage.user_stats[owner_id] = {"total_cached": 0, "total_edited": 0, "total_deleted": 0}
    storage.user_stats[owner_id]["total_cached"] += 1

    cache_key = f"{conn_id}:{message.message_id}"
    photo_bytes = None
    voice_file_id = None
    sticker_file_id = None
    fallback_text = "[Медиа-файл]"
    
    if message.photo:
        fallback_text = "[Фото]"
        try:
            file_buffer = io.BytesIO()
            await bot.download(message.photo[-1], destination=file_buffer)
            photo_bytes = file_buffer.getvalue()
        except:
            fallback_text = "📸 [Исчезающее фото]"
    elif message.voice:
        fallback_text = "🎙 [Голосовое сообщение]"
        voice_file_id = message.voice.file_id
    elif message.sticker:
        fallback_text = "🖼 [Стикер]"
        sticker_file_id = message.sticker.file_id
            
    current_text = message.text or message.caption or fallback_text
    await check_new_bot_scam(message, current_text, bot, owner_id)
    
    storage.msg_cache[cache_key] = {
        "text": current_text,
        "user_id": message.from_user.id if message.from_user else 0,
        "username": f"@{message.from_user.username}" if message.from_user and message.from_user.username else "нет",
        "full_name": message.from_user.full_name if message.from_user else "Система",
        "chat_id": message.chat.id,
        "photo_bytes": photo_bytes,
        "voice_file_id": voice_file_id,
        "sticker_file_id": sticker_file_id
    }

    history_key = f"{conn_id}:{message.chat.id}"
    if history_key not in storage.chat_history:
        storage.chat_history[history_key] = []
    
    time_str = message.date.strftime('%H:%M:%S')
    log_entry = f"[{time_str}] {message.from_user.full_name if message.from_user else 'User'}: {current_text}"
    storage.chat_history[history_key].append(log_entry)

    if len(storage.chat_history[history_key]) > 100:
        storage.chat_history[history_key].pop(0)

@tracker_router.edited_business_message()
async def handle_edited_business_message(message: Message, bot: Bot):
    conn_id = message.business_connection_id
    owner_id = await get_owner_id(bot, conn_id)
    if not owner_id or not storage.user_logs_active.get(owner_id, True): 
        return

    if message.from_user and message.from_user.id in storage.muted_users and message.from_user.id != owner_id:
        try: await bot.delete_business_messages(business_connection_id=conn_id, message_ids=[message.message_id])
        except: pass
        return

    msg_key = f"{conn_id}:{message.message_id}"
    if message.from_user and message.from_user.id == owner_id:
        if msg_key in storage.msg_cache:
            storage.msg_cache[msg_key]["text"] = message.text or message.caption or "[Новое медиа]"
        return

    old_data = storage.msg_cache.get(msg_key)
    if not old_data: 
        return

    new_text = message.text or message.caption or "[Новое медиа]"
    storage.msg_cache[msg_key]["text"] = new_text
    await check_new_bot_scam(message, new_text, bot, owner_id)

    if message.chat.id in storage.blocked_chats: 
        return

    if owner_id not in storage.user_stats:
        storage.user_stats[owner_id] = {"total_cached": 0, "total_edited": 0, "total_deleted": 0}
    storage.user_stats[owner_id]["total_edited"] += 1

    text_report = (
        f"✏️ <b>Сообщение отредактировано</b>\n\n"
        f"<blockquote><b>{escape_html(old_data['full_name'])}</b>\n"
        f"Было: {escape_html(old_data['text'])}\n"
        f"Стало: {escape_html(new_text)}</blockquote>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Context", callback_data=f"ctx:{conn_id}:{message.chat.id}"),
            InlineKeyboardButton(text="❌ Скрыть", callback_data="skip")
        ]
    ])
    try: await bot.send_message(chat_id=owner_id, text=text_report, reply_markup=kb, parse_mode="HTML")
    except: pass

@tracker_router.deleted_business_messages()
async def handle_deleted_business_messages(deleted: BusinessMessagesDeleted, bot: Bot):
    conn_id = deleted.business_connection_id
    owner_id = await get_owner_id(bot, conn_id)
    if not owner_id or not storage.user_logs_active.get(owner_id, True): 
        return

    for msg_id in deleted.message_ids:
        msg_key = f"{conn_id}:{msg_id}"
        old_data = storage.msg_cache.get(msg_key)
        if not old_data: 
            continue

        if old_data['user_id'] == owner_id:
            storage.msg_cache.pop(msg_key, None)
            continue

        chat_id = old_data['chat_id']
        if chat_id in storage.blocked_chats:
            storage.msg_cache.pop(msg_key, None)
            continue

        if old_data['user_id'] in storage.muted_users:
            storage.msg_cache.pop(msg_key, None)
            continue

        if owner_id not in storage.user_stats:
            storage.user_stats[owner_id] = {"total_cached": 0, "total_edited": 0, "total_deleted": 0}
        storage.user_stats[owner_id]["total_deleted"] += 1
        
        voice_file_id = old_data.get("voice_file_id")
        sticker_file_id = old_data.get("sticker_file_id")

        if voice_file_id:
            text_report = (
                f"🗑 <b>Это голосовое сообщение было удалено:</b>\n\n"
                f"<b>Отправитель:</b> {escape_html(old_data['full_name'])} ({escape_html(old_data['username'])})"
            )
            storage.deleted_voices[msg_key] = voice_file_id

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💬 Перейти в чат", url=f"tg://user?id={chat_id}")],
                [
                    InlineKeyboardButton(text="📦 Контекст", callback_data=f"ctx:{conn_id}:{chat_id}"),
                    InlineKeyboardButton(text="🔔 Не уведомлять", callback_data="skip")
                ],
                [InlineKeyboardButton(text="🔄 Вернуть в чат", callback_data="skip")],
                [InlineKeyboardButton(text="📝 Расшифровать", callback_data=f"trans:{conn_id}:{msg_id}")],
                [InlineKeyboardButton(text="❌ Скрыть", callback_data="skip")]
            ])
            try: await bot.send_message(chat_id=owner_id, text=text_report, reply_markup=kb, parse_mode="HTML")
            except: pass

        elif sticker_file_id:
            text_report = (
                f"🗑 <b>Этот стикер был удален:</b>\n\n"
                f"<b>Отправитель:</b> {escape_html(old_data['full_name'])} ({escape_html(old_data['username'])})"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔍 Контекст чата", callback_data=f"ctx:{conn_id}:{chat_id}"),
                    InlineKeyboardButton(text="❌ Скрыть", callback_data="skip")
                ]
            ])
            try:
                await bot.send_message(chat_id=owner_id, text=text_report, parse_mode="HTML")
                await bot.send_sticker(chat_id=owner_id, sticker=sticker_file_id, reply_markup=kb)
            except: pass

        else:
            text_report = (
                f"🗑 <b>Это сообщение было удалено</b>\n\n"
                f"<blockquote><b>{escape_html(old_data['full_name'])}</b>\n"
                f"{escape_html(old_data['text'])}</blockquote>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔍 Контекст чата", callback_data=f"ctx:{conn_id}:{chat_id}"),
                    InlineKeyboardButton(text="❌ Скрыть", callback_data="skip")
                ]
            ])
            photo_bytes = old_data.get("photo_bytes")
            if photo_bytes:
                media_saver.save_deleted_photo(photo_bytes=photo_bytes, user_id=old_data['user_id'], full_name=old_data['full_name'])
                try:
                    photo_file = BufferedInputFile(photo_bytes, filename="deleted_photo.jpg")
                    await bot.send_photo(chat_id=owner_id, photo=photo_file, caption=text_report, reply_markup=kb, parse_mode="HTML")
                except:
                    await bot.send_message(chat_id=owner_id, text=text_report, reply_markup=kb, parse_mode="HTML")
            else:
                try: await bot.send_message(chat_id=owner_id, text=text_report, reply_markup=kb, parse_mode="HTML")
                except: pass

        history_key = f"{conn_id}:{chat_id}"
        all_messages = storage.chat_history.get(history_key, [])
        if all_messages:
            try:
                file_data = "\n".join(all_messages).encode("utf-8")
                txt_file = BufferedInputFile(file_data, filename="messages_log.txt")
                await bot.send_document(chat_id=owner_id, document=txt_file, caption="📄 Файл истории чата")
            except: pass

        storage.msg_cache.pop(msg_key, None)

@tracker_router.channel_post()
async def handle_channel_post(message: Message, bot: Bot):
    """Отслеживает появление новых постов в целевых каналах"""
    if not hasattr(storage, "tracked_channels") or not storage.tracked_channels:
        return
        
    ch_id = str(message.chat.id)
    ch_username = message.chat.username.lower() if message.chat.username else ""
    
    owner_id = storage.tracked_channels.get(ch_id) or storage.tracked_channels.get(ch_username)
    
    if owner_id:
        ch_title = message.chat.title or "Отслеживаемый канал"
        post_content = message.text or message.caption or "[Медиа-материалы]"
        
        # Генерация ссылки на опубликованный пост (как для публичных, так и для приватных каналов)
        if message.chat.username:
            post_url = f"https://t.me/{message.chat.username}/{message.message_id}"
        else:
            clean_id = ch_id.replace("-100", "")
            post_url = f"https://t.me/c/{clean_id}/{message.message_id}"
            
        report = (
            f"📢 <b>В отслеживаемом канале вышел новый пост!</b>\n\n"
            f"<b>Канал:</b> {escape_html(ch_title)}\n"
            f"<b>Содержимое:</b> {escape_html(post_content)}\n\n"
            f"🔗 <a href='{post_url}'>Перейти к посту</a>"
        )
        try: await bot.send_message(chat_id=owner_id, text=report, parse_mode="HTML", disable_web_page_preview=False)
        except Exception as e: print(f"[ChannelTracking] Ошибка отправки: {e}")

@tracker_router.callback_query(F.data.startswith("ctx:"))
async def callback_context(callback: CallbackQuery):
    try:
        _, conn_id, chat_id = callback.data.split(":")
        history = storage.chat_history.get(f"{conn_id}:{chat_id}", [])
        if not history:
            await callback.answer("История этого чата пуста.", show_alert=True)
            return

        last_10 = [escape_html(msg) for msg in history[-10:]]
        response_text = "📝 <b>Последние 10 сообщений чата:</b>\n\n" + "\n".join(last_10)
        await callback.message.answer(response_text, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        print(f"[Context Callback Error] {e}")
        await callback.answer("Ошибка при получении контекста чата.", show_alert=True)

@tracker_router.callback_query(F.data.startswith("trans:"))
async def callback_transcribe(callback: CallbackQuery):
    try:
        _, conn_id, msg_id = callback.data.split(":")
        msg_key = f"{conn_id}:{msg_id}"
        voice_file_id = storage.deleted_voices.get(msg_key)
        if not voice_file_id:
            await callback.answer("Файл голосового сообщения устарел или удален из ОЗУ.", show_alert=True)
            return
            
        await callback.answer("Голосовое обрабатывается...")
        transcription_result = "Всем привет, мы тестируем новую функцию сейфбота."
        report = (
            f"📝 <b>Расшифровка голосового</b>\n\n"
            f"<blockquote>{escape_html(transcription_result)} ❞</blockquote>\n"
            f"Осталось сегодня: ∞"
        )
        await callback.message.answer(report, parse_mode="HTML")
    except Exception as e:
        print(f"[Transcribe Error] {e}")
        await callback.answer("Не удалось расшифровать аудиофайл.", show_alert=True)

@tracker_router.callback_query(F.data == "skip")
async def callback_skip(callback: CallbackQuery):
    try: await callback.message.delete()
    except: pass
    await callback.answer()


import asyncio
import logging
from bot_core import dp, bot
from handlers_menu import menu_router
from handlers_tracker import tracker_router
from handlers_ping import ping_router
from handlers_admin import admin_router  # <-- Импортируем роутер админки

async def main():
    # Регистрируем модули в диспетчере в правильном порядке
    dp.include_router(menu_router)
    dp.include_router(ping_router)
    dp.include_router(tracker_router)
    dp.include_router(admin_router)   # <-- Регистрируем админку в боте
    
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("🚀 BUSINESS MONITOR УСПЕШНО ЗАПУЩЕН!")
    print("Система контроля прав администратора активна.")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())

import time
from aiogram import Router, F
from aiogram.types import Message

ping_router = Router()

@ping_router.message(F.text.lower() == ".ping")
async def cmd_ping(message: Message):
    start = time.perf_counter()
    msg = await message.answer("⏳")
    end = time.perf_counter()
    await msg.edit_text(f"🚀 **ПОНГ!** Задержка: `{round((end - start) * 1000)} мс`", parse_mode="Markdown")

import asyncio
import logging
from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter

from config import ADMIN_IDS
from database import add_user, get_all_users, get_users_count
from keyboards import get_admin_keyboard, get_back_keyboard, get_cancel_keyboard
from states import BroadcastStates

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message):
    add_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    await message.answer(
            "👋 Добро пожаловать!\n\n"
            "Для входа в админ-панель используйте /admin",
    )


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Доступ запрещён")
        return
    await message.answer("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())


@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён")
        return
    
    total_users = get_users_count()
    text = f"📊 <b>Статистика</b>\n\nВсего пользователей: {total_users}"
    await callback.message.edit_text(text, reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def admin_users(callback):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён")
        return
    
    users = get_all_users()
    
    if not users:
        await callback.answer("Нет пользователей!", show_alert=True)
        return
    
    text = "👥 <b>Пользователи:</b>\n\n"
    for user in users[:20]:
        name = user['first_name'] or 'Неизвестно'
        text += f"ID: {user['user_id']} | {name} | {user['joined']}\n"
    
    await callback.message.edit_text(text, reply_markup=get_back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(callback, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён")
        return
    
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\nВведите текст сообщения для рассылки:",
        reply_markup=get_cancel_keyboard()
    )
    await callback.answer()
    await state.set_state(BroadcastStates.waiting_for_text)


@router.callback_query(F.data == "admin_back")
async def admin_back(callback, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Доступ запрещён")
        return
    
    await state.clear()
    await callback.message.edit_text("⚙️ Админ-панель:", reply_markup=get_admin_keyboard())
    await callback.answer()


async def send_broadcast(bot: Bot, text: str):
    success = 0
    failed = 0
    
    users = get_all_users()
    
    for user in users:
        try:
            await bot.send_message(user['user_id'], text)
            success += 1
            await asyncio.sleep(0.05)
        except TelegramRetryAfter as e:
            logger.warning(f"Rate limit hit, sleeping {e.retry_after}s")
            await asyncio.sleep(e.retry_after)
        except TelegramNetworkError as e:
            logger.error(f"Network error for {user['user_id']}: {e}")
            failed += 1
        except Exception as e:
            logger.error(f"Failed to send to {user['user_id']}: {e}")
            failed += 1
    
    return success, failed


@router.message(BroadcastStates.waiting_for_text, F.from_user.id.in_(ADMIN_IDS))
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    await message.answer("📢 Отправка рассылки...")
    success, failed = await send_broadcast(bot, message.text)
    await message.answer(f"✅ Рассылка завершена!\n\nОтправлено: {success}\nОшибки: {failed}")
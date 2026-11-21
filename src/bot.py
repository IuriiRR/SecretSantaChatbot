import asyncio
import html
import logging
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters.callback_data import CallbackData
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db_manager import DbDriver
from states import SecretSantaStates
from utils import create_pairings, decode_room, encode_room

logger = logging.getLogger(__name__)
dp = Dispatcher()


class RoomInfoCallback(CallbackData, prefix="room_info"):
    number: int = 0


class RoomDeleteCallback(CallbackData, prefix="room_delete"):
    number: int = 0


class RoomAddPlayersCallback(CallbackData, prefix="room_add_player"):
    number: int = 0
    pair: bool = False


class RoomLeaveCallback(CallbackData, prefix="room_leave"):
    number: int = 0


class RoomSortCallback(CallbackData, prefix="room_sort"):
    number: int = 0


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build the main menu inline keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Створити кімнату", callback_data="room_create")],
            [InlineKeyboardButton(text="📋 Список кімнат", callback_data="room_list")],
            [InlineKeyboardButton(text="🔑 Приєднатись до кімнати", callback_data="room_join")],
        ]
    )


def _cancel_keyboard() -> InlineKeyboardMarkup:
    """Build a single-button cancellation keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Скасувати", callback_data="cancel")]]
    )


async def _send_to_callback_user(
    callback: types.CallbackQuery,
    message_text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> None:
    """Send a message to the user who triggered a callback query."""
    if callback.bot is not None:
        await callback.bot.send_message(
            callback.from_user.id,
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
    elif callback.message is not None:
        await callback.message.answer(
            text=message_text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )


@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext) -> None:
    """Handle /start by clearing active state and showing the main menu."""
    await state.clear()
    await message.answer(
        "Вітаю в Secret Santa боті! 🎅\nОберіть дію:",
        reply_markup=_main_menu_keyboard(),
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message, state: FSMContext) -> None:
    """Handle /help by clearing active state and showing the main menu."""
    await state.clear()
    await message.reply("Обирай:", reply_markup=_main_menu_keyboard())


@dp.callback_query(F.data == "room_create")
async def create_room_callback(callback: types.CallbackQuery) -> None:
    """Create a new Secret Santa room and send its invite code to the creator."""
    await callback.answer()
    try:
        with DbDriver() as db:
            room_id = db.insert_room(callback.from_user.id)
    except Exception as err:
        logger.exception("Failed to create room for user %s", callback.from_user.id)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    invite_code = encode_room(room_id)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Кімната {room_id}",
                    callback_data=RoomInfoCallback(number=room_id).pack(),
                )
            ]
        ]
    )
    await _send_to_callback_user(
        callback,
        (
            f"Створено кімнату {room_id}!\n"
            f"Код запрошення: <code>{html.escape(invite_code)}</code>\n"
            "Надішліть цей код учасникам, щоб вони могли приєднатись."
        ),
        reply_markup=kb,
        parse_mode="HTML",
    )


@dp.callback_query(F.data == "room_join")
async def join_room_callback(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Prompt the user to enter a room invite code."""
    await callback.answer()
    await state.set_state(SecretSantaStates.join_group)
    await _send_to_callback_user(
        callback,
        (
            "Введіть код запрошення до кімнати (наприклад, secretsanta-...).\n"
            "Або натисніть 'Скасувати'."
        ),
        reply_markup=_cancel_keyboard(),
    )


@dp.message(SecretSantaStates.join_group)
async def join_group(message: types.Message, state: FSMContext) -> None:
    """Validate an invite code, verify the room exists, and open room access."""
    if not message.text or not message.text.strip():
        await message.answer(
            "Будь ласка, надішліть текстовий код запрошення.",
            reply_markup=_cancel_keyboard(),
        )
        return

    raw_code = message.text.strip()
    try:
        room_number = decode_room(raw_code)
    except ValueError:
        await message.answer(
            f"{raw_code} здається мені неправильним. Спробуй ще",
            reply_markup=_cancel_keyboard(),
        )
        return

    try:
        with DbDriver() as db:
            room = db.get_room_by_id(room_number)
    except Exception as err:
        logger.exception("Database error checking room %s", room_number)
        await message.answer(f"Виникла помилка: {err}")
        return

    if room is None:
        await message.answer(
            f"Кімнату {room_number} не знайдено. Перевірте код і спробуйте ще раз.",
            reply_markup=_cancel_keyboard(),
        )
        return

    await state.clear()
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Кімната {room_number}",
                    callback_data=RoomInfoCallback(number=room_number).pack(),
                )
            ]
        ]
    )
    await message.answer(f"Вітаємо в кімнаті {room_number}", reply_markup=kb)


@dp.callback_query(F.data == "room_list")
async def room_list(callback: types.CallbackQuery) -> None:
    """List rooms owned by or joined by the current user."""
    await callback.answer()
    try:
        with DbDriver() as db:
            rooms = db.get_my_rooms(callback.from_user.id)
    except Exception as err:
        logger.exception("Failed to list rooms for user %s", callback.from_user.id)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    if not rooms:
        await _send_to_callback_user(
            callback,
            "Ви ще не створили/не доєднались до жодної групи. Спробуйте /help",
            reply_markup=_main_menu_keyboard(),
        )
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for room_id, owner_tg_id in rooms:
        row_buttons = [
            InlineKeyboardButton(
                text=f"Кімната {room_id}",
                callback_data=RoomInfoCallback(number=room_id).pack(),
            )
        ]
        if owner_tg_id == callback.from_user.id:
            row_buttons.append(
                InlineKeyboardButton(
                    text=f"Сортувати {room_id}",
                    callback_data=RoomSortCallback(number=room_id).pack(),
                )
            )
            row_buttons.append(
                InlineKeyboardButton(
                    text=f"Видалити {room_id}",
                    callback_data=RoomDeleteCallback(number=room_id).pack(),
                )
            )
        buttons.append(row_buttons)

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await _send_to_callback_user(callback, "Оберіть кімнату для деталей", reply_markup=kb)


@dp.callback_query(RoomDeleteCallback.filter())
async def room_delete(callback: types.CallbackQuery, callback_data: RoomDeleteCallback) -> None:
    """Delete a room if the caller is its owner."""
    await callback.answer()
    try:
        with DbDriver() as db:
            deleted = db.delete_room(callback_data.number, callback.from_user.id)
    except Exception as err:
        logger.exception("Failed to delete room %s", callback_data.number)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    if deleted:
        await _send_to_callback_user(callback, f"Кімнату {callback_data.number} видалено.")
    else:
        await _send_to_callback_user(
            callback,
            "Не вдалося видалити кімнату (ви не є власником або кімнату не знайдено).",
        )


@dp.callback_query(RoomSortCallback.filter())
async def room_sort(callback: types.CallbackQuery, callback_data: RoomSortCallback) -> None:
    """Generate and deliver Secret Santa pairings for a room."""
    await callback.answer()
    try:
        with DbDriver() as db:
            room = db.get_room_by_id(callback_data.number)
            if room is None:
                await _send_to_callback_user(callback, f"Кімнату {callback_data.number} не знайдено.")
                return
            if room[1] != callback.from_user.id:
                await _send_to_callback_user(
                    callback,
                    "Тільки власник кімнати може запускати жеребкування.",
                )
                return
            members = db.get_room_players(callback_data.number)
    except Exception as err:
        logger.exception("Database error sorting room %s", callback_data.number)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    pairs = create_pairings(members)
    if pairs is None:
        await _send_to_callback_user(
            callback,
            (
                "Недостатньо учасників або неможливо розподілити пари без збігів. "
                "Додайте ще гравців і спробуйте знову."
            ),
        )
        return

    failed_deliveries = 0
    for send_to_tg_id, from_name, from_group_name, to_name, to_group_name in pairs:
        try:
            if callback.bot is None:
                raise RuntimeError("Bot instance is unavailable")
            await callback.bot.send_message(
                send_to_tg_id,
                f"{from_name} ({from_group_name}) 🤲🎁➡️ {to_name} ({to_group_name})",
            )
            await callback.bot.send_message(
                send_to_tg_id,
                "🎅🎄 Ваше жеребкування готове. Це повідомлення приховає його зі списку чатів :) 🤫🎁",
            )
        except Exception as err:
            failed_deliveries += 1
            logger.exception("Failed to send pairing message to %s", send_to_tg_id)
            await _send_to_callback_user(callback, f"Виникла помилка доставки: {err}")

    if failed_deliveries == 0:
        await _send_to_callback_user(
            callback,
            f"Жеребкування для кімнати {callback_data.number} завершено! Повідомлення надіслано всім учасникам.",
        )
    else:
        await _send_to_callback_user(
            callback,
            f"Жеребкування завершено з помилками доставки: {failed_deliveries}.",
        )


@dp.callback_query(RoomInfoCallback.filter())
async def room_info(callback: types.CallbackQuery, callback_data: RoomInfoCallback) -> None:
    """Display room invite code, current players, and join/leave controls."""
    await callback.answer()
    try:
        with DbDriver() as db:
            room = db.get_room_by_id(callback_data.number)
            if room is None:
                await _send_to_callback_user(callback, f"Кімнату {callback_data.number} не знайдено.")
                return
            members = db.get_room_players(callback_data.number)
    except Exception as err:
        logger.exception("Database error fetching info for room %s", callback_data.number)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    player_lines: list[str] = []
    is_in_game = False
    for member, pair, tg_id in members:
        if tg_id == callback.from_user.id:
            is_in_game = True
        if pair:
            for pair_member in member.split():
                player_lines.append(f"🎄 {html.escape(pair_member)} ({html.escape(member)})")
        else:
            player_lines.append(f"🎄 {html.escape(member)}")

    buttons: list[list[InlineKeyboardButton]] = []
    if is_in_game:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Покинути кімнату {callback_data.number}",
                    callback_data=RoomLeaveCallback(number=callback_data.number).pack(),
                )
            ]
        )
    else:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"Додати гравця до кімнати {callback_data.number}",
                    callback_data=RoomAddPlayersCallback(
                        number=callback_data.number, pair=False
                    ).pack(),
                ),
                InlineKeyboardButton(
                    text=f"Додати пару до кімнати {callback_data.number}",
                    callback_data=RoomAddPlayersCallback(
                        number=callback_data.number, pair=True
                    ).pack(),
                ),
            ]
        )

    invite_code = encode_room(callback_data.number)
    players_text = "\n".join(player_lines) if player_lines else "(Поки немає гравців)"
    message_text = (
        f"<b>Кімната {callback_data.number}</b>\n"
        f"Код запрошення: <code>{html.escape(invite_code)}</code>\n\n"
        f"<b>Активні гравці:</b>\n{players_text}"
    )
    await _send_to_callback_user(
        callback,
        message_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="HTML",
    )


@dp.callback_query(RoomAddPlayersCallback.filter())
async def add_players_callback(
    callback: types.CallbackQuery,
    callback_data: RoomAddPlayersCallback,
    state: FSMContext,
) -> None:
    """Prompt the user to enter a solo player name or a couple's names."""
    await callback.answer()
    await state.update_data(room=callback_data.number)
    if callback_data.pair:
        await state.set_state(SecretSantaStates.add_pair)
        prompt_text = (
            "Введіть 2 імені гравців через пробіл (наприклад: <code>Юра Неля</code>).\n"
            "Або натисніть 'Скасувати'."
        )
        parse_mode = "HTML"
    else:
        await state.set_state(SecretSantaStates.add_player)
        prompt_text = "Введіть імʼя одинокого гравця (лише імʼя).\nАбо натисніть 'Скасувати'."
        parse_mode = None

    await _send_to_callback_user(
        callback,
        prompt_text,
        reply_markup=_cancel_keyboard(),
        parse_mode=parse_mode,
    )


@dp.callback_query(F.data == "cancel")
async def cancel(callback: types.CallbackQuery, state: FSMContext) -> None:
    """Cancel the current FSM flow."""
    await callback.answer()
    await state.clear()
    await _send_to_callback_user(callback, "Скасовано. Спробуйте /help.")


@dp.message(SecretSantaStates.add_player)
async def add_player(message: types.Message, state: FSMContext) -> None:
    """Add a single player to the selected room."""
    if message.from_user is None:
        return
    if not message.text or not message.text.strip():
        await message.answer("Будь ласка, введіть імʼя гравця.", reply_markup=_cancel_keyboard())
        return

    data = await state.get_data()
    room_id = data.get("room")
    if room_id is None:
        await state.clear()
        await message.answer("Кімнату не обрано. Спробуйте /help.")
        return

    player_name = message.text.strip()
    try:
        with DbDriver() as db:
            if db.get_room_by_id(room_id) is None:
                await state.clear()
                await message.answer(f"Кімнату {room_id} не знайдено.")
                return
            db.add_player(player_name, tg_id=message.from_user.id, pair=False, room_id=room_id)
    except Exception as err:
        logger.exception("Failed to add player to room %s", room_id)
        await message.answer(f"Виникла помилка: {err}")
        return

    await state.clear()
    await message.answer(f"Гравця {player_name} додано в кімнату {room_id}")


@dp.message(SecretSantaStates.add_pair)
async def add_pair(message: types.Message, state: FSMContext) -> None:
    """Add a couple (two space-separated names) to the selected room."""
    if message.from_user is None:
        return
    if not message.text or not message.text.strip():
        await message.answer(
            "Потрібно ввести 2 імені через пробіл. Спробуй ще",
            reply_markup=_cancel_keyboard(),
        )
        return

    pair = message.text.strip().split()
    if len(pair) != 2:
        await message.answer(
            f"Введені дані для пари ({' + '.join(pair)}) виглядають неправильно :(. \n"
            "Потрібно ввести 2 імені через пробіл. Спробуй ще",
            reply_markup=_cancel_keyboard(),
        )
        return

    data = await state.get_data()
    room_id = data.get("room")
    if room_id is None:
        await state.clear()
        await message.answer("Кімнату не обрано. Спробуйте /help.")
        return

    pair_label = " ".join(pair)
    try:
        with DbDriver() as db:
            if db.get_room_by_id(room_id) is None:
                await state.clear()
                await message.answer(f"Кімнату {room_id} не знайдено.")
                return
            db.add_player(pair_label, tg_id=message.from_user.id, pair=True, room_id=room_id)
    except Exception as err:
        logger.exception("Failed to add pair to room %s", room_id)
        await message.answer(f"Виникла помилка: {err}")
        return

    await state.clear()
    await message.answer(f"Гравців {' + '.join(pair)} додано в кімнату {room_id}")


@dp.callback_query(RoomLeaveCallback.filter())
async def leave_room(
    callback: types.CallbackQuery,
    callback_data: RoomLeaveCallback,
    state: FSMContext,
) -> None:
    """Remove the current user's player/pair entry from a room."""
    await callback.answer()
    try:
        with DbDriver() as db:
            db.leave_room(tg_id=callback.from_user.id, room_id=callback_data.number)
    except Exception as err:
        logger.exception("Failed to leave room %s", callback_data.number)
        await _send_to_callback_user(callback, f"Виникла помилка: {err}")
        return

    await state.clear()
    await _send_to_callback_user(
        callback,
        f"Ви покинули кімнату {callback_data.number}. Спробуйте знайти сенс життя з /help",
    )


async def main() -> None:
    """Configure logging, validate bot token, and start Telegram polling."""
    logging.basicConfig(level=logging.INFO)
    token = os.getenv("TG_TOKEN")
    if not token:
        raise RuntimeError("TG_TOKEN environment variable is required")

    bot = Bot(token=token)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

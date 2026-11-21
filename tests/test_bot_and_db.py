import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from db_manager import DbDriver  # noqa: E402
from utils import create_pairings, decode_room, encode_room  # noqa: E402

try:
    import bot  # noqa: E402
except ModuleNotFoundError:
    bot = None


class TestDbDriver(unittest.TestCase):
    """Tests for SQLite DbDriver CRUD, ownership checks, and constraints."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp_dir.name, "nested", "test_santa.sqlite")

    def tearDown(self) -> None:
        self._tmp_dir.cleanup()

    def test_db_path_creation_and_env_default(self) -> None:
        env_path = os.path.join(self._tmp_dir.name, "env_dir", "env_santa.sqlite")
        prev_env = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = env_path
        try:
            with DbDriver() as db:
                room_id = db.insert_room(1001)
                self.assertEqual(db.get_room_by_id(room_id), (room_id, 1001))
            self.assertTrue(os.path.exists(env_path))
        finally:
            if prev_env is None:
                os.environ.pop("DB_PATH", None)
            else:
                os.environ["DB_PATH"] = prev_env

    def test_room_crud_and_distinct_my_rooms(self) -> None:
        with DbDriver(self.db_path) as db:
            room_id = db.insert_room(owner_tg_id=10)
            self.assertEqual(db.get_room_by_id(room_id), (room_id, 10))
            self.assertIsNone(db.get_room_by_id(9999))

            # Owner and multiple players join the same room
            db.add_player("Owner", tg_id=10, pair=False, room_id=room_id)
            db.add_player("Alice", tg_id=20, pair=False, room_id=room_id)
            db.add_player("Bob Carol", tg_id=30, pair=True, room_id=room_id)

            # Owner should only see the room once despite multiple players
            self.assertEqual(db.get_my_rooms(10), [(room_id, 10)])
            self.assertEqual(db.get_my_rooms(20), [(room_id, 10)])
            self.assertEqual(db.get_my_rooms(99), [])

            players = db.get_room_players(room_id)
            self.assertEqual(len(players), 3)

    def test_leave_room(self) -> None:
        with DbDriver(self.db_path) as db:
            room_id = db.insert_room(owner_tg_id=10)
            db.add_player("Alice", tg_id=20, pair=False, room_id=room_id)
            db.add_player("Bob", tg_id=30, pair=False, room_id=room_id)

            removed = db.leave_room(tg_id=20, room_id=room_id)
            self.assertEqual(removed, 1)
            self.assertEqual(db.get_room_players(room_id), [("Bob", 0, 30)])
            self.assertEqual(db.get_my_rooms(20), [])

    def test_delete_room_ownership_and_cascade_cleanup(self) -> None:
        with DbDriver(self.db_path) as db:
            room_id = db.insert_room(owner_tg_id=10)
            db.add_player("Alice", tg_id=20, pair=False, room_id=room_id)

            # Non-owner cannot delete
            self.assertFalse(db.delete_room(room_id, owner_tg_id=20))
            self.assertIsNotNone(db.get_room_by_id(room_id))

            # Missing room returns False
            self.assertFalse(db.delete_room(9999, owner_tg_id=10))

            # Owner can delete and players are removed
            self.assertTrue(db.delete_room(room_id, owner_tg_id=10))
            self.assertIsNone(db.get_room_by_id(room_id))
            self.assertEqual(db.get_room_players(room_id), [])


class TestUtils(unittest.TestCase):
    """Tests for room invite encoding/decoding and Secret Santa pairings."""

    def test_encode_and_decode_room(self) -> None:
        for room_num in (1, 42, 12345):
            invite = encode_room(room_num)
            self.assertRegex(invite, r"^secretsanta-\w{12}-\d+$")
            self.assertEqual(decode_room(invite), room_num)
            self.assertEqual(decode_room(f"  {invite}  "), room_num)

    def test_decode_room_invalid(self) -> None:
        for invalid in ("", "invalid", "secretsanta-short-1", "secretsanta-123456789012-abc"):
            with self.assertRaises(ValueError):
                decode_room(invalid)

    def test_create_pairings_insufficient_or_impossible(self) -> None:
        self.assertIsNone(create_pairings([]))
        self.assertIsNone(create_pairings([("Solo", False, 1)]))
        self.assertIsNone(create_pairings([("Alice Bob", True, 1)]))
        # 1 couple + 1 solo cannot form a 3-cycle without pairing the couple
        self.assertIsNone(create_pairings([("Alice Bob", True, 1), ("Carol", False, 2)]))

    def test_create_pairings_two_couples_never_pair_partner_or_self(self) -> None:
        people = [
            ("Юра Неля", True, 101),
            ("Сер Діана", True, 102),
        ]
        pairings = create_pairings(people)
        self.assertIsNotNone(pairings)
        assert pairings is not None
        self.assertEqual(len(pairings), 4)

        givers = {row[1] for row in pairings}
        receivers = {row[3] for row in pairings}
        self.assertEqual(givers, {"Юра", "Неля", "Сер", "Діана"})
        self.assertEqual(receivers, {"Юра", "Неля", "Сер", "Діана"})

        for _tg_id, from_name, from_group, to_name, to_group in pairings:
            self.assertNotEqual(from_name, to_name)
            self.assertNotEqual(from_group, to_group)

    def test_create_pairings_mixed_couples_and_solo(self) -> None:
        people = [
            ("Юра Неля", True, 101),
            ("Сер Діана", True, 102),
            ("Юля Діма", True, 103),
            ("Жора", False, 104),
        ]
        pairings = create_pairings(people)
        self.assertIsNotNone(pairings)
        assert pairings is not None
        self.assertEqual(len(pairings), 7)

        givers = [row[1] for row in pairings]
        receivers = [row[3] for row in pairings]
        self.assertEqual(len(set(givers)), 7)
        self.assertEqual(set(givers), set(receivers))

        for _tg_id, from_name, from_group, to_name, to_group in pairings:
            self.assertNotEqual(from_name, to_name)
            self.assertNotEqual(from_group, to_group)


@unittest.skipIf(bot is None, "aiogram is not installed")
class TestBotRoomSort(unittest.IsolatedAsyncioTestCase):
    """Tests for bot room_sort pairing delivery and preview-hiding follow-up."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp_dir.name, "test_bot_santa.sqlite")
        self._prev_db_path = os.environ.get("DB_PATH")
        os.environ["DB_PATH"] = self.db_path

    def tearDown(self) -> None:
        if self._prev_db_path is None:
            os.environ.pop("DB_PATH", None)
        else:
            os.environ["DB_PATH"] = self._prev_db_path
        self._tmp_dir.cleanup()

    async def test_room_sort_sends_pairing_and_preview_hide_message(self) -> None:
        owner_id = 10
        with DbDriver() as db:
            room_id = db.insert_room(owner_tg_id=owner_id)
            db.add_player("Alice", tg_id=101, pair=False, room_id=room_id)
            db.add_player("Bob", tg_id=102, pair=False, room_id=room_id)

        callback = MagicMock()
        callback.from_user.id = owner_id
        callback.answer = AsyncMock()
        callback.bot = MagicMock()
        callback.bot.send_message = AsyncMock()

        assert bot is not None
        await bot.room_sort(callback, bot.RoomSortCallback(number=room_id))

        callback.answer.assert_awaited_once()
        calls = callback.bot.send_message.await_args_list
        # 2 messages per participant (pairing + preview-hiding) + 1 completion message to owner
        self.assertEqual(len(calls), 5)

        preview_hide_msg = "🎅🎄 Ваше жеребкування готове. Це повідомлення приховає його зі списку чатів :) 🤫🎁"
        for player_tg_id in (101, 102):
            player_messages = [
                call.args[1] for call in calls if call.args and call.args[0] == player_tg_id
            ]
            self.assertEqual(len(player_messages), 2)
            self.assertIn("🤲🎁➡️", player_messages[0])
            self.assertEqual(player_messages[1], preview_hide_msg)


if __name__ == "__main__":
    unittest.main()

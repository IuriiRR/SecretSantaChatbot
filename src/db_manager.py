import os
import sqlite3
from pathlib import Path
from types import TracebackType


class DbDriver:
    """SQLite persistence driver for Secret Santa rooms and players."""

    def __init__(self, db_path: str | None = None) -> None:
        resolved_path = db_path or os.getenv("DB_PATH", "secret_santa_db.sqlite")
        if resolved_path != ":memory:":
            parent = Path(resolved_path).parent
            if str(parent) and str(parent) != ".":
                parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(resolved_path)
        self._cursor = self._conn.cursor()
        self._cursor.execute("PRAGMA foreign_keys = ON;")
        self._cursor.execute("PRAGMA journal_mode = WAL;")
        self.config_db()

    def __enter__(self) -> "DbDriver":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()

    def config_db(self) -> None:
        """Create required database tables if they do not exist."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_tg_id INTEGER NOT NULL
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                tg_id INTEGER NOT NULL,
                pair BOOLEAN NOT NULL DEFAULT 0,
                room_id INTEGER NOT NULL,
                FOREIGN KEY (room_id) REFERENCES rooms(id) ON DELETE CASCADE
            );
            """,
        ]
        for query in queries:
            self.execute_dml(query=query, params=())

    def execute_dml(self, query: str, params: tuple = ()) -> None:
        """Execute a data manipulation query and commit the transaction."""
        self._cursor.execute(query, params)
        self._conn.commit()

    def execute_select(self, query: str, params: tuple = ()) -> list[tuple]:
        """Execute a SELECT query and return all fetched rows."""
        self._cursor.execute(query, params)
        return self._cursor.fetchall()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def get_room_by_id(self, room_id: int) -> tuple[int, int] | None:
        """Fetch a single room (id, owner_tg_id) by its primary key."""
        query = "SELECT id, owner_tg_id FROM rooms WHERE id = ?"
        self._cursor.execute(query, (room_id,))
        return self._cursor.fetchone()

    def get_all_rooms(self) -> list[tuple[int, int]]:
        """Fetch all rooms."""
        query = "SELECT id, owner_tg_id FROM rooms ORDER BY id"
        self._cursor.execute(query)
        return self._cursor.fetchall()

    def insert_room(self, owner_tg_id: int) -> int:
        """Create a new room owned by owner_tg_id and return its id."""
        query = "INSERT INTO rooms (owner_tg_id) VALUES (?)"
        self._cursor.execute(query, (owner_tg_id,))
        self._conn.commit()
        if self._cursor.lastrowid is None:
            raise RuntimeError("Failed to retrieve inserted room id")
        return self._cursor.lastrowid

    def delete_room(self, room_id: int, owner_tg_id: int) -> bool:
        """Delete a room and its players if it exists and belongs to owner_tg_id."""
        room = self.get_room_by_id(room_id)
        if room is None or room[1] != owner_tg_id:
            return False

        self._cursor.execute("DELETE FROM players WHERE room_id = ?", (room_id,))
        self._cursor.execute(
            "DELETE FROM rooms WHERE id = ? AND owner_tg_id = ?",
            (room_id, owner_tg_id),
        )
        self._conn.commit()
        return self._cursor.rowcount > 0

    def add_player(self, name: str, tg_id: int, pair: bool, room_id: int) -> int:
        """Add a player or couple entry to a room and return its row id."""
        query = "INSERT INTO players (name, tg_id, pair, room_id) VALUES (?, ?, ?, ?)"
        self._cursor.execute(query, (name, tg_id, pair, room_id))
        self._conn.commit()
        if self._cursor.lastrowid is None:
            raise RuntimeError("Failed to retrieve inserted player id")
        return self._cursor.lastrowid

    def leave_room(self, tg_id: int, room_id: int) -> int:
        """Remove a player's entries from a room and return affected row count."""
        query = "DELETE FROM players WHERE room_id = ? AND tg_id = ?"
        self._cursor.execute(query, (room_id, tg_id))
        self._conn.commit()
        return self._cursor.rowcount

    def get_my_rooms(self, tg_id: int) -> list[tuple[int, int]]:
        """Return distinct rooms owned by or joined by tg_id."""
        query = """
            SELECT DISTINCT rooms.id, rooms.owner_tg_id
            FROM rooms
            LEFT JOIN players p ON rooms.id = p.room_id
            WHERE rooms.owner_tg_id = ?
               OR p.tg_id = ?
            ORDER BY rooms.id
        """
        self._cursor.execute(query, (tg_id, tg_id))
        return self._cursor.fetchall()

    def get_room_players(self, room_id: int) -> list[tuple[str, int | bool, int]]:
        """Return (name, pair, tg_id) for all players in a room."""
        query = "SELECT name, pair, tg_id FROM players WHERE room_id = ?"
        self._cursor.execute(query, (room_id,))
        return self._cursor.fetchall()

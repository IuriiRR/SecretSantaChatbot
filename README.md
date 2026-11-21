# SecretSantaChatbot 🎅

A Telegram bot built with `aiogram` and SQLite for organizing Secret Santa gift exchanges with support for both solo participants and couples.

## Features

- **Room Management**: Create, list, and delete Secret Santa rooms via inline menus (`/start` or `/help`).
- **Invite Codes**: Shareable room invite codes (`secretsanta-<token>-<room_id>`) to join an existing room.
- **Solo & Couple Entries**: Participants can register individually or as a couple (two space-separated names).
- **Fair Circular Pairings**: `create_pairings` creates a circular Secret Santa assignment that prevents participants from drawing themselves or their partner.
- **Preview Protection**: After delivering each pairing message, the bot sends a follow-up message (`🎅🎄 Ваше жеребкування готове. Це повідомлення приховає його зі списку чатів :) 🤫🎁`) so the match is hidden in the Telegram chat list preview.

## Configuration

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `TG_TOKEN` | Yes | — | Telegram Bot API token obtained from `@BotFather` |
| `DB_PATH` | No | `secret_santa_db.sqlite` | Path to the SQLite database file |

## Running Locally

1. Create and activate a virtual environment, then install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. Set `TG_TOKEN` and start the bot:
   ```bash
   export TG_TOKEN="your_telegram_bot_token_here"
   PYTHONPATH=src python -m bot
   ```

## Running with Docker Compose

1. Create a `.env` file in the repository root:
   ```env
   TG_TOKEN=your_telegram_bot_token_here
   ```
2. Build and start the service:
   ```bash
   docker compose up --build
   ```

> **Note:** `docker-compose.yaml` currently does not mount a persistent volume for the SQLite file inside the container; configure a volume mount and `DB_PATH` if you need database persistence across container rebuilds.

## Running Tests

No secrets (`TG_TOKEN`) are required to run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

> **Note:** `TestBotRoomSort` in `tests/test_bot_and_db.py` requires `aiogram` in your active Python environment and is skipped automatically if `aiogram` is not installed.

import random
import re
import secrets
from string import ascii_letters
from typing import Any


def encode_room(room_number: int) -> str:
    """Generate a Secret Santa invite code encoding the given room id."""
    token = "".join(secrets.choice(ascii_letters) for _ in range(12))
    return f"secretsanta-{token}-{room_number}"


def decode_room(invite_code: str) -> int:
    """Extract the room id from a Secret Santa invite code."""
    pattern = r"^secretsanta-(\w{12})-(\d+)$"
    match = re.match(pattern, invite_code.strip())
    if not match:
        raise ValueError(f"{invite_code} is invalid")
    return int(match.group(2))


def split_couples(people: list[tuple[str, int | bool, int]] | list[Any]) -> list[tuple[int, str, str | None]]:
    """Expand couple entries into individual participant tuples (tg_id, name, couple_label)."""
    split_people: list[tuple[int, str, str | None]] = []
    for name_raw, is_pair, tg_id in people:
        if is_pair:
            names = name_raw.split()
            couple_label = " ".join(names)
            for name in names:
                split_people.append((tg_id, name, couple_label))
        else:
            split_people.append((tg_id, name_raw.strip(), None))
    return split_people


def create_pairings(
    people: list[tuple[str, int | bool, int]] | list[Any],
    max_attempts: int = 100,
) -> list[list[Any]] | None:
    """Create a valid circular Secret Santa assignment avoiding self and partner matches."""
    split_people = split_couples(people)
    if len(split_people) < 2:
        return None

    for _ in range(max_attempts):
        random.shuffle(split_people)
        pairings: list[list[Any]] = []
        for idx, current in enumerate(split_people):
            next_idx = (idx + 1) % len(split_people)
            next_person = split_people[next_idx]
            # Ensure a participant is not paired with themselves or their partner
            if (
                idx != next_idx
                and current is not next_person
                and (current[2] is None or current[2] != next_person[2])
            ):
                pairings.append(
                    [
                        current[0],
                        current[1],
                        current[2] or current[1],
                        next_person[1],
                        next_person[2] or next_person[1],
                    ]
                )
            else:
                break

        if len(pairings) == len(split_people):
            return pairings

    return None

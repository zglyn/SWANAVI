from __future__ import annotations

import json
import os
import sqlite3
from typing import Protocol

from roam_contracts.models import UserProfile

from roam_agent.profile_crypto import open_profile, seal_profile


class ProfileStore(Protocol):
    def get(self, user_id: str) -> UserProfile | None: ...
    def put(self, profile: UserProfile) -> None: ...
    def delete(self, user_id: str) -> None: ...


class MemoryProfileStore:
    def __init__(self, key: bytes | None = None) -> None:
        self._rows: dict[str, dict] = {}
        self.key = key

    def get(self, user_id: str) -> UserProfile | None:
        raw = self._rows.get(user_id)
        if raw is None:
            return None
        return open_profile(raw, self.key)

    def put(self, profile: UserProfile) -> None:
        self._rows[profile.user_id] = seal_profile(profile, self.key)

    def delete(self, user_id: str) -> None:
        self._rows.pop(user_id, None)

    def stored_text(self, user_id: str) -> str:
        return json.dumps(self._rows.get(user_id))


class SqliteProfileStore:
    def __init__(self, path: str, key: bytes | None = None) -> None:
        if key is None and not os.environ.get("ROAM_PROFILE_KEY"):
            raise RuntimeError("ROAM_PROFILE_KEY is required to store profiles on disk")
        self.key = key
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("create table if not exists profiles (user_id text primary key, payload text)")
        self._db.commit()

    def get(self, user_id: str) -> UserProfile | None:
        row = self._db.execute("select payload from profiles where user_id = ?", (user_id,)).fetchone()
        if row is None:
            return None
        return open_profile(json.loads(row[0]), self.key)

    def put(self, profile: UserProfile) -> None:
        payload = json.dumps(seal_profile(profile, self.key))
        self._db.execute(
            "insert into profiles (user_id, payload) values (?, ?) on conflict(user_id) do update set payload = excluded.payload",
            (profile.user_id, payload),
        )
        self._db.commit()

    def delete(self, user_id: str) -> None:
        self._db.execute("delete from profiles where user_id = ?", (user_id,))
        self._db.commit()

    def stored_text(self, user_id: str) -> str:
        row = self._db.execute("select payload from profiles where user_id = ?", (user_id,)).fetchone()
        return "" if row is None else row[0]

from __future__ import annotations

import hashlib
import secrets
import sqlite3


class MemoryAuth:
    def __init__(self) -> None:
        self.sessions: dict[str, str] = {}

    def start(self, email: str) -> tuple[str, str]:
        user_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
        token = secrets.token_urlsafe(24)
        self.sessions[token] = user_id
        return token, user_id

    def user_for(self, token: str) -> str | None:
        return self.sessions.get(token)

    def drop_token(self, token: str) -> None:
        self.sessions.pop(token, None)

    def drop_user(self, user_id: str) -> None:
        self.sessions = {token: owner for token, owner in self.sessions.items() if owner != user_id}


class SqliteAuth:
    def __init__(self, path: str) -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute("create table if not exists sessions (token text primary key, user_id text)")
        self._db.commit()

    def start(self, email: str) -> tuple[str, str]:
        user_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]
        token = secrets.token_urlsafe(24)
        self._db.execute("insert into sessions (token, user_id) values (?, ?)", (token, user_id))
        self._db.commit()
        return token, user_id

    def user_for(self, token: str) -> str | None:
        row = self._db.execute("select user_id from sessions where token = ?", (token,)).fetchone()
        return None if row is None else row[0]

    def drop_token(self, token: str) -> None:
        self._db.execute("delete from sessions where token = ?", (token,))
        self._db.commit()

    def drop_user(self, user_id: str) -> None:
        self._db.execute("delete from sessions where user_id = ?", (user_id,))
        self._db.commit()

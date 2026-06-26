import aiosqlite
import json
from typing import Optional

DB_PATH = "food_bot.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                age INTEGER,
                weight REAL,
                calories INTEGER,
                allergies TEXT DEFAULT '[]',
                dislikes TEXT DEFAULT '[]'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                name TEXT,
                age INTEGER,
                weight REAL,
                calories INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS daily_exclusions (
                user_id INTEGER,
                ingredient TEXT,
                excluded_date TEXT,
                PRIMARY KEY (user_id, ingredient, excluded_date)
            )
        """)
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                d = dict(row)
                d["allergies"] = json.loads(d["allergies"])
                d["dislikes"] = json.loads(d["dislikes"])
                return d
    return None


async def upsert_user(user_id: int, name: str, age: int, weight: float, calories: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, name, age, weight, calories)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name=excluded.name, age=excluded.age,
                weight=excluded.weight, calories=excluded.calories
        """, (user_id, name, age, weight, calories))
        await db.commit()


async def update_allergies(user_id: int, allergies: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET allergies = ? WHERE user_id = ?",
                         (json.dumps(allergies, ensure_ascii=False), user_id))
        await db.commit()


async def update_dislikes(user_id: int, dislikes: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET dislikes = ? WHERE user_id = ?",
                         (json.dumps(dislikes, ensure_ascii=False), user_id))
        await db.commit()


async def get_family_members(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM family_members WHERE user_id = ?", (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_family_member(user_id: int, name: str, age: int, weight: float, calories: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO family_members (user_id, name, age, weight, calories)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, name, age, weight, calories))
        await db.commit()


async def update_family_member(member_id: int, name: str, age: int, weight: float, calories: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE family_members SET name=?, age=?, weight=?, calories=? WHERE id=?
        """, (name, age, weight, calories, member_id))
        await db.commit()


async def delete_family_member(user_id: int, member_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM family_members WHERE id = ? AND user_id = ?", (member_id, user_id)
        )
        await db.commit()


async def add_daily_exclusion(user_id: int, ingredient: str, date_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO daily_exclusions (user_id, ingredient, excluded_date)
            VALUES (?, ?, ?)
        """, (user_id, ingredient.lower(), date_str))
        await db.commit()


async def get_daily_exclusions(user_id: int, date_str: str) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT ingredient FROM daily_exclusions WHERE user_id = ? AND excluded_date = ?",
            (user_id, date_str)
        ) as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]


async def get_all_user_ids() -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

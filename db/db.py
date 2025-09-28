import asyncpg
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL


async def init_db():
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS appeals (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            username TEXT,
            room TEXT,
            text TEXT,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id SERIAL PRIMARY KEY,
            appeal_id INT REFERENCES appeals(id) ON DELETE CASCADE,
            sender TEXT,
            text TEXT,
            created_at TIMESTAMP DEFAULT now()
        );
        """)
    finally:
        await conn.close()


async def create_appeal(user_id, username, room, text):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal_id = await conn.fetchval(
            "INSERT INTO appeals (user_id, username, room, text) VALUES ($1,$2,$3,$4) RETURNING id",
            user_id, username, room, text
        )
    finally:
        await conn.close()
    return appeal_id


async def add_message(appeal_id, sender, text):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "INSERT INTO messages (appeal_id, sender, text) VALUES ($1,$2,$3)",
            appeal_id, sender, text
        )
    finally:
        await conn.close()


async def update_status(appeal_id, status):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("UPDATE appeals SET status=$1 WHERE id=$2", status, appeal_id)
        row = await conn.fetchrow("SELECT user_id FROM appeals WHERE id=$1", appeal_id)
    finally:
        await conn.close()
    return row["user_id"] if row else None


async def get_appeals(status=None, limit=50):
    conn = await asyncpg.connect(DB_URL)
    try:
        if status:
            rows = await conn.fetch("SELECT * FROM appeals WHERE status=$1 ORDER BY created_at DESC LIMIT $2", status, limit)
        else:
            rows = await conn.fetch("SELECT * FROM appeals ORDER BY created_at DESC LIMIT $1", limit)
    finally:
        await conn.close()
    return rows


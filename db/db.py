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
            request_type TEXT DEFAULT 'other',
            optional_comment TEXT,
            status TEXT DEFAULT 'new',
            priority INT DEFAULT 1,
            assigned_admin BIGINT,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        );
        """)
        
        await conn.execute("""
        ALTER TABLE appeals 
        ADD COLUMN IF NOT EXISTS request_type TEXT DEFAULT 'other',
        ADD COLUMN IF NOT EXISTS optional_comment TEXT;
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
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            user_id BIGINT UNIQUE,
            username TEXT,
            role TEXT DEFAULT 'admin',
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id SERIAL PRIMARY KEY,
            admin_id BIGINT,
            session_data JSONB,
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_admin_messages (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            message TEXT NOT NULL,
            appeal_id INTEGER,
            sent BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT UNIQUE NOT NULL,
            username TEXT,
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_status ON appeals(status);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_room ON appeals(room);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_created_at ON appeals(created_at);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_user_id ON appeals(user_id);")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_appeals_request_type ON appeals(request_type);")
    finally:
        await conn.close()


async def create_appeal(user_id, username, room, text, request_type='other', optional_comment=None):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal_id = await conn.fetchval(
            "INSERT INTO appeals (user_id, username, room, text, request_type, optional_comment) VALUES ($1,$2,$3,$4,$5,$6) RETURNING id",
            user_id, username, room, text, request_type, optional_comment
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


async def get_appeals(status=None, limit=50, offset=0, room=None, search_query=None, request_type=None):
    conn = await asyncpg.connect(DB_URL)
    try:
        conditions = []
        params = []
        param_counter = 1
        
        if status:
            conditions.append(f"status=${param_counter}")
            params.append(status)
            param_counter += 1
            
        if room:
            conditions.append(f"room=${param_counter}")
            params.append(room)
            param_counter += 1
            
        if request_type:
            conditions.append(f"request_type=${param_counter}")
            params.append(request_type)
            param_counter += 1
            
        if search_query:
            conditions.append(f"(text ILIKE ${param_counter} OR username ILIKE ${param_counter})")
            params.append(f"%{search_query}%")
            param_counter += 1
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"SELECT * FROM appeals {where_clause} ORDER BY created_at DESC LIMIT ${param_counter} OFFSET ${param_counter + 1}"
        params.extend([limit, offset])
        
        rows = await conn.fetch(query, *params)
        
        count_query = f"SELECT COUNT(*) FROM appeals {where_clause}"
        count_params = params[:-2] if conditions else []
        total_count = await conn.fetchval(count_query, *count_params) if count_params else await conn.fetchval("SELECT COUNT(*) FROM appeals")
        
    finally:
        await conn.close()
    return rows, total_count


async def get_appeal_with_messages(appeal_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal = await conn.fetchrow("SELECT * FROM appeals WHERE id=$1", appeal_id)
        messages = await conn.fetch("SELECT * FROM messages WHERE appeal_id=$1 ORDER BY created_at ASC", appeal_id)
    finally:
        await conn.close()
    return appeal, messages


async def add_admin(user_id, username, role='admin'):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "INSERT INTO admins (user_id, username, role) VALUES ($1, $2, $3) ON CONFLICT (user_id) DO UPDATE SET username=$2, role=$3, is_active=true",
            user_id, username, role
        )
    finally:
        await conn.close()


async def remove_admin(user_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("UPDATE admins SET is_active=false WHERE user_id=$1", user_id)
    finally:
        await conn.close()


async def is_admin(user_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        row = await conn.fetchrow("SELECT * FROM admins WHERE user_id=$1 AND is_active=true", user_id)
    finally:
        await conn.close()
    return row is not None


async def get_all_admins():
    conn = await asyncpg.connect(DB_URL)
    try:
        rows = await conn.fetch("SELECT * FROM admins WHERE is_active=true ORDER BY created_at")
    finally:
        await conn.close()
    return rows


async def get_appeals_stats():
    conn = await asyncpg.connect(DB_URL)
    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM appeals")
        new_count = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='new'")
        received_count = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='received'")
        done_count = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='done'")
        declined_count = await conn.fetchval("SELECT COUNT(*) FROM appeals WHERE status='declined'")
        
        daily_stats = await conn.fetch("""
            SELECT DATE(created_at) as date, COUNT(*) as count 
            FROM appeals 
            WHERE created_at >= NOW() - INTERVAL '7 days' 
            GROUP BY DATE(created_at) 
            ORDER BY date ASC
        """)
        
        room_stats = await conn.fetch("""
            SELECT room, COUNT(*) as count 
            FROM appeals 
            GROUP BY room 
            ORDER BY count DESC 
            LIMIT 10
        """)
        
        type_stats = await conn.fetch("""
            SELECT request_type, COUNT(*) as count 
            FROM appeals 
            GROUP BY request_type 
            ORDER BY count DESC
        """)
        
        hourly_stats = await conn.fetch("""
            SELECT EXTRACT(HOUR FROM created_at) as hour, COUNT(*) as count
            FROM appeals
            WHERE created_at >= NOW() - INTERVAL '24 hours'
            GROUP BY hour
            ORDER BY hour
        """)
        
        avg_response_time = await conn.fetchval("""
            SELECT AVG(EXTRACT(EPOCH FROM (updated_at - created_at))) / 3600
            FROM appeals
            WHERE status != 'new' AND updated_at IS NOT NULL
        """)
        
        today_count = await conn.fetchval("""
            SELECT COUNT(*) FROM appeals 
            WHERE DATE(created_at) = CURRENT_DATE
        """)
        
        yesterday_count = await conn.fetchval("""
            SELECT COUNT(*) FROM appeals 
            WHERE DATE(created_at) = CURRENT_DATE - INTERVAL '1 day'
        """)
        
    finally:
        await conn.close()
    
    return {
        'total': total,
        'new': new_count, 
        'received': received_count,
        'done': done_count,
        'declined': declined_count,
        'daily': [{'date': row['date'].strftime('%Y-%m-%d'), 'count': row['count']} for row in daily_stats],
        'rooms': [{'room': row['room'], 'count': row['count']} for row in room_stats],
        'types': [{'type': row['request_type'], 'count': row['count']} for row in type_stats],
        'hourly': [{'hour': int(row['hour']), 'count': row['count']} for row in hourly_stats],
        'avg_response_time': round(avg_response_time or 0, 2),
        'today_count': today_count,
        'yesterday_count': yesterday_count,
        'growth_rate': round(((today_count - yesterday_count) / max(yesterday_count, 1)) * 100, 1) if yesterday_count else 0
    }


async def assign_appeal_to_admin(appeal_id, admin_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "UPDATE appeals SET assigned_admin=$1, updated_at=NOW() WHERE id=$2", 
            admin_id, appeal_id
        )
    finally:
        await conn.close()


async def bulk_update_status(appeal_ids, status):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "UPDATE appeals SET status=$1, updated_at=NOW() WHERE id = ANY($2)", 
            status, appeal_ids
        )
    finally:
        await conn.close()


async def can_user_reply(appeal_id, user_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        appeal = await conn.fetchrow("SELECT user_id FROM appeals WHERE id=$1", appeal_id)
        if not appeal or appeal['user_id'] != user_id:
            return False
        
        last_admin_msg = await conn.fetchrow(
            "SELECT id FROM messages WHERE appeal_id=$1 AND sender='admin' ORDER BY created_at DESC LIMIT 1", 
            appeal_id
        )
        if not last_admin_msg:
            return False
        
        user_reply_after_admin = await conn.fetchrow(
            "SELECT id FROM messages WHERE appeal_id=$1 AND sender='user' AND created_at > (SELECT created_at FROM messages WHERE id=$2)",
            appeal_id, last_admin_msg['id']
        )
        
        return user_reply_after_admin is None
        
    finally:
        await conn.close()


async def get_appeals_by_type():
    conn = await asyncpg.connect(DB_URL)
    try:
        type_groups = {}
        
        type_names = {
            'iron': 'Утюг и гладильная доска',
            'laundry': 'Услуги прачечной',
            'technical_ac': 'Кондиционер',
            'technical_wifi': 'WiFi',
            'technical_tv': 'Телевизор',
            'technical_other': 'Другие технические проблемы',
            'restaurant_call': 'Соединить с рестораном',
            'custom': 'Другие вопросы',
            'other': 'Прочее'
        }
        
        for req_type, display_name in type_names.items():
            appeals = await conn.fetch("""
                SELECT * FROM appeals 
                WHERE request_type = $1 
                ORDER BY created_at DESC
            """, req_type)
            
            if appeals:
                type_groups[display_name] = [dict(appeal) for appeal in appeals]
    
    finally:
        await conn.close()
    
    return type_groups


async def add_notification_recipient(chat_id, username=None):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            """INSERT INTO notification_settings (chat_id, username) 
               VALUES ($1, $2) 
               ON CONFLICT (chat_id) DO UPDATE SET username=$2, is_active=true""",
            chat_id, username
        )
    finally:
        await conn.close()


async def remove_notification_recipient(chat_id):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "DELETE FROM notification_settings WHERE chat_id=$1",
            chat_id
        )
    finally:
        await conn.close()


async def get_notification_recipients(active_only=True):
    conn = await asyncpg.connect(DB_URL)
    try:
        if active_only:
            rows = await conn.fetch(
                "SELECT * FROM notification_settings WHERE is_active=true ORDER BY created_at"
            )
        else:
            rows = await conn.fetch(
                "SELECT * FROM notification_settings ORDER BY created_at"
            )
    finally:
        await conn.close()
    return rows


async def toggle_notification_recipient(chat_id, is_active):
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute(
            "UPDATE notification_settings SET is_active=$1 WHERE chat_id=$2",
            is_active, chat_id
        )
    finally:
        await conn.close()

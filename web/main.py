from fastapi import FastAPI, Request, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from datetime import datetime, timedelta
import secrets
import asyncpg
import json
import sys
import os
import redis.asyncio as redis
from typing import Optional, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import DB_URL, ADMIN_PASSWORD
from db.db import (
    get_appeals, get_appeal_with_messages, update_status, add_message,
    get_appeals_stats, assign_appeal_to_admin, bulk_update_status,
    get_appeals_by_type
)

app = FastAPI(title="Spasskaya Hotel Admin Panel", version="3.1")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

security = HTTPBasic()

redis_client = None

async def get_current_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_password = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (credentials.username == "admin" and correct_password):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    return credentials.username

async def init_redis():
    global redis_client
    try:
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        await redis_client.ping()
    except Exception as e:
        print(f"Redis connection failed: {e}")
        redis_client = None

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections[:]:
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

@app.on_event("startup")
async def startup():
    await init_redis()
    conn = await asyncpg.connect(DB_URL)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pending_admin_messages (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                appeal_id INTEGER,
                sent BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("Table pending_admin_messages created/verified")
    except Exception as e:
        print(f"Error creating table: {e}")
    finally:
        await conn.close()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, admin: str = Depends(get_current_admin)):
    stats = await get_appeals_stats()
    
    appeals, total = await get_appeals(limit=10)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "stats": stats,
        "appeals": appeals,
        "total_appeals": total
    })

@app.get("/appeals", response_class=HTMLResponse)
async def appeals_page(
    request: Request, 
    status: Optional[str] = None,
    room: Optional[str] = None,
    search: Optional[str] = None,
    request_type: Optional[str] = None,
    page: int = 1,
    admin: str = Depends(get_current_admin)
):
    limit = 20
    offset = (page - 1) * limit
    
    appeals, total = await get_appeals(
        status=status,
        room=room,
        search_query=search,
        request_type=request_type,
        limit=limit,
        offset=offset
    )
    
    total_pages = (total + limit - 1) // limit
    
    request_type_options = {
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
    
    return templates.TemplateResponse("appeals.html", {
        "request": request,
        "appeals": appeals,
        "current_page": page,
        "total_pages": total_pages,
        "total_appeals": total,
        "status_filter": status,
        "room_filter": room,
        "search_filter": search,
        "request_type_filter": request_type,
        "request_type_options": request_type_options
    })

@app.get("/appeals/{appeal_id}", response_class=HTMLResponse)
async def appeal_detail(request: Request, appeal_id: int, admin: str = Depends(get_current_admin)):
    appeal, messages = await get_appeal_with_messages(appeal_id)
    
    if not appeal:
        raise HTTPException(status_code=404, detail="Appeal not found")
    
    return templates.TemplateResponse("appeal_detail.html", {
        "request": request,
        "appeal": appeal,
        "messages": messages
    })

@app.post("/api/appeals/{appeal_id}/status")
async def update_appeal_status(appeal_id: int, request: Request, admin: str = Depends(get_current_admin)):
    try:
        form = await request.form()
        status = form.get("status")

        if not status:
            raise HTTPException(status_code=400, detail="Status is required")

        key = f"appeal:{appeal_id}:status:{status}"
        now = datetime.now().isoformat()

        if redis_client:
            duplicate = await redis_client.get(key)
            if duplicate:
                print(f"[SKIP DUPLICATE] appeal {appeal_id} status={status} time={now}")
                return {"skipped": True, "appeal_id": appeal_id, "status": status}
            await redis_client.setex(key, 5, "1")

        user_id = await update_status(appeal_id, status)

        if user_id:
            conn = await asyncpg.connect(DB_URL)
            try:
                status_messages = {
                    'received': 'получено в работу ✅',
                    'declined': 'отклонено ❌',
                    'done': 'выполнено ✅'
                }

                status_msg = status_messages.get(status, f"изменён на {status}")
                message_text = f"📬 Ваше обращение {status_msg}"

                if status == 'done':
                    message_text += "\n\nЕсли проблема не решена, нажмите кнопку 'Не решено' ниже."

                existing = await conn.fetchrow(
                    """SELECT id FROM pending_admin_messages 
                       WHERE user_id = $1 AND message = $2 AND appeal_id = $3 
                       AND created_at > NOW() - INTERVAL '1 minute'""",
                    user_id, message_text, appeal_id
                )

                if not existing:
                    await conn.execute(
                        """INSERT INTO pending_admin_messages (user_id, message, appeal_id) 
                           VALUES ($1, $2, $3)""",
                        user_id, message_text, appeal_id
                    )
            finally:
                await conn.close()

            await manager.broadcast(json.dumps({
                "type": "status_update",
                "appeal_id": appeal_id,
                "status": status,
                "timestamp": now
            }))

            if redis_client:
                await redis_client.lpush("admin_actions", json.dumps({
                    "type": "status_update",
                    "appeal_id": appeal_id,
                    "status": status,
                    "admin": admin,
                    "timestamp": now
                }))

        return {"success": True, "appeal_id": appeal_id, "status": status}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating status: {str(e)}")


@app.post("/api/appeals/{appeal_id}/reply")
async def reply_to_appeal(appeal_id: int, request: Request, admin: str = Depends(get_current_admin)):
    try:
        form = await request.form()
        message = form.get("message")
        
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        await add_message(appeal_id, "admin", message)
        
        conn = await asyncpg.connect(DB_URL)
        try:
            appeal = await conn.fetchrow("SELECT user_id FROM appeals WHERE id=$1", appeal_id)
            
            if appeal:
                admin_message_text = f"📢 Ответ администратора на обращение #{appeal_id}:\n\n{message}"
                
                existing = await conn.fetchrow(
                    """SELECT id FROM pending_admin_messages 
                       WHERE user_id = $1 AND message = $2 AND appeal_id = $3 
                       AND created_at > NOW() - INTERVAL '1 minute'""",
                    appeal['user_id'], admin_message_text, appeal_id
                )
                
                if not existing:
                    await conn.execute(
                        """INSERT INTO pending_admin_messages (user_id, message, appeal_id) 
                           VALUES ($1, $2, $3)""",
                        appeal['user_id'], admin_message_text, appeal_id
                    )
        finally:
            await conn.close()
        
        if appeal:
            await manager.broadcast(json.dumps({
                "type": "new_message",
                "appeal_id": appeal_id,
                "sender": "admin",
                "message": message,
                "timestamp": datetime.now().isoformat()
            }))
        
        return {"success": True, "appeal_id": appeal_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending reply: {str(e)}")

@app.post("/api/appeals/bulk_update")
async def bulk_update_appeals(appeal_ids: List[int], status: str, admin: str = Depends(get_current_admin)):
    await bulk_update_status(appeal_ids, status)
    
    await manager.broadcast(json.dumps({
        "type": "bulk_update",
        "appeal_ids": appeal_ids,
        "status": status,
        "timestamp": datetime.now().isoformat()
    }))
    
    return {"success": True, "updated_count": len(appeal_ids)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/test-js", response_class=HTMLResponse)
async def test_js_page(request: Request, admin: str = Depends(get_current_admin)):
    from fastapi.responses import FileResponse
    return FileResponse("web/test_js.html")

@app.get("/api/stats")
async def get_stats(admin: str = Depends(get_current_admin)):
    return await get_appeals_stats()

@app.get("/analytics", response_class=HTMLResponse)
async def analytics_page(request: Request, admin: str = Depends(get_current_admin)):
    stats = await get_appeals_stats()
    
    return templates.TemplateResponse("analytics.html", {
        "request": request,
        "stats": stats
    })

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, admin: str = Depends(get_current_admin)):
    return templates.TemplateResponse("chat.html", {
        "request": request
    })

@app.get("/appeals/by-type", response_class=HTMLResponse)
async def appeals_by_type_page(request: Request, admin: str = Depends(get_current_admin)):
    type_groups = await get_appeals_by_type()
    
    return templates.TemplateResponse("appeals_by_type.html", {
        "request": request,
        "type_groups": type_groups
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
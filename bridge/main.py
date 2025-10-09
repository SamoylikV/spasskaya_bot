import asyncio
import logging
import json
import sys
import os
import redis.asyncio as redis
from aiogram import Bot

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import TOKEN, DB_URL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MessageBridge:
    def __init__(self):
        self.bot = Bot(TOKEN)
        self.redis_client = None
        
    async def init_redis(self):
        try:
            self.redis_client = redis.Redis(host='redis', port=6379, db=0)
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            self.redis_client = None

    async def process_telegram_messages(self):
        if not self.redis_client:
            return
            
        try:
            message_data = await self.redis_client.brpop('telegram_messages', timeout=1)
            
            if message_data:
                queue_name, message_json = message_data
                message = json.loads(message_json)
                
                await self.send_telegram_message(message)
                logger.info(f"Sent message to Telegram user {message['user_id']}")
                
        except Exception as e:
            logger.error(f"Error processing telegram messages: {e}")

    async def send_telegram_message(self, message_data):
        try:
            user_id = message_data['user_id']
            text = message_data['message']
            appeal_id = message_data.get('appeal_id')
            
            reply_markup = None
            if appeal_id and message_data.get('add_reopen_button', False):
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❗ Вопрос не решили", callback_data=f"user_reopen:{appeal_id}")]
                ])
            
            await self.bot.send_message(
                chat_id=user_id,
                text=text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Failed to send telegram message: {e}")

    async def process_status_updates(self):
        if not self.redis_client:
            return
            
        try:
            status_data = await self.redis_client.brpop('status_updates', timeout=1)
            
            if status_data:
                queue_name, status_json = status_data
                update = json.loads(status_json)
                
                await self.handle_status_update(update)
                logger.info(f"Processed status update for appeal {update['appeal_id']}")
                
        except Exception as e:
            logger.error(f"Error processing status updates: {e}")

    async def handle_status_update(self, update):
        try:
            appeal_id = update['appeal_id']
            status = update['status']
            user_id = update['user_id']
            
            status_messages = {
                'received': 'Ваше обращение принято в работу ⏳',
                'done': 'Ваше обращение выполнено ✅',
                'declined': 'Ваше обращение отклонено ❌'
            }
            
            message_text = status_messages.get(status, f'Статус вашего обращения изменен: {status}')
            
            reply_markup = None
            if status == 'done':
                from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                reply_markup = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❗ Вопрос не решили", callback_data=f"user_reopen:{appeal_id}")]
                ])
            
            await self.bot.send_message(
                chat_id=user_id,
                text=message_text,
                reply_markup=reply_markup
            )
            
        except Exception as e:
            logger.error(f"Failed to handle status update: {e}")

    async def notify_new_appeal(self, appeal_data):
        if not self.redis_client:
            return
            
        try:
            notification = {
                'type': 'new_appeal',
                'appeal_id': appeal_data['appeal_id'],
                'user_id': appeal_data['user_id'],
                'username': appeal_data['username'],
                'room': appeal_data['room'],
                'text': appeal_data['text'],
                'timestamp': appeal_data['timestamp']
            }
            
            await self.redis_client.publish('admin_notifications', json.dumps(notification))
            logger.info(f"Published new appeal notification for {appeal_data['appeal_id']}")
            
        except Exception as e:
            logger.error(f"Failed to notify new appeal: {e}")

    async def run(self):
        await self.init_redis()
        
        if not self.redis_client:
            logger.error("Cannot start bridge without Redis connection")
            return
            
        logger.info("Message bridge started")
        
        while True:
            try:
                await self.process_telegram_messages()
                
                await self.process_status_updates()
                
                await asyncio.sleep(0.1)
                
            except KeyboardInterrupt:
                logger.info("Shutting down message bridge...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in bridge: {e}")
                await asyncio.sleep(1)

    async def cleanup(self):
        if self.redis_client:
            await self.redis_client.close()
        await self.bot.session.close()

async def main():
    bridge = MessageBridge()
    try:
        await bridge.run()
    except KeyboardInterrupt:
        logger.info("Bridge stopped by user")
    finally:
        await bridge.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
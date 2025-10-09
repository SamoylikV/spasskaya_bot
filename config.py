import os
from dotenv import dotenv_values

config = {}
if os.path.exists('.env'):
    config = dotenv_values(".env")

TOKEN = os.getenv('TOKEN') or config.get('TOKEN')
ADMIN_ID = os.getenv('ADMIN_ID') or config.get('ADMIN_ID')
DB_URL = os.getenv('DB_URL') or config.get('DB_URL')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD') or config.get('ADMIN_PASSWORD', 'admin123')
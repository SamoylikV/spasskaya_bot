from dotenv import dotenv_values

config = dotenv_values(".env")

TOKEN = config.get('TOKEN')
ADMIN_ID = config.get('ADMIN_ID')
DB_URL = config.get('DB_URL')
print()
print(TOKEN)
print()
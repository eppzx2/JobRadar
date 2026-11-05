from dotenv import load_dotenv

from database.store import connect
from frontend.dashboard import dashboard

load_dotenv()
db = connect()
try:
    dashboard(db)
finally:
    db.close()

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_socketio import SocketIO
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
# Los orígenes CORS se fijan en create_app() desde Config.SOCKETIO_CORS_ORIGINS.
socketio = SocketIO()
csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, connection_record):
    """WAL permite lectores concurrentes mientras un estudiante escribe.

    Es la principal mitigación del riesgo "concurrencia alta en SQLite" (SAD §13)
    mientras la plataforma no justifique el costo de PostgreSQL.
    """
    if type(dbapi_connection).__module__.split('.')[0] != 'sqlite3':
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

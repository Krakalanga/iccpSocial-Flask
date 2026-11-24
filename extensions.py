from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_socketio import SocketIO


db = SQLAlchemy()

login_manager = LoginManager()

socketio = SocketIO()


login_manager.login_view = "login"

login_manager.login_message = (
    "Debes iniciar sesión para acceder."
)
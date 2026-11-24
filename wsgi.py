# wsgi.py
import eventlet
eventlet.monkey_patch()

# Importar la aplicación Flask
from app import app

# Si necesitas socketio para desarrollo
# from app import socketio

if __name__ == "__main__":
    # No ejecutes nada aquí, solo exportar 'app' para Gunicorn
    pass
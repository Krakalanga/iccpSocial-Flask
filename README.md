# ICCP Social — Red social en Flask

Aplicación web de red social construida con **Flask**, **Flask-SQLAlchemy**,
**Flask-Login** y **Flask-SocketIO**. Permite registro/login de usuarios,
publicaciones con imágenes, comentarios y chat privado en tiempo real
(incluyendo envío de imágenes y estado en línea/desconectado).

## Requisitos

- Python 3.10 o superior

## Instalación

```bash
# 1. Crear y activar un entorno virtual
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt
```

## Configuración

La aplicación lee la configuración sensible desde variables de entorno.
Antes de desplegar en producción, define al menos:

```bash
export SECRET_KEY="Aqui pones la clave que quieras :)"
export FLASK_DEBUG=0
```

Si no se definen, la app usa valores de desarrollo por defecto (no seguros
para producción).

Variables disponibles:

| Variable       | Descripción                                   | Por defecto                  |
|----------------|------------------------------------------------|-------------------------------|
| `SECRET_KEY`   | Clave secreta de Flask (sesiones, CSRF, etc.)  | clave insegura de desarrollo |
| `DATABASE_URL` | URI de la base de datos SQLAlchemy             | SQLite local (`database.db`) |
| `FLASK_DEBUG`  | `1` para activar el modo debug, `0` para prod. | `1`                            |
| `PORT`         | Puerto en el que escucha el servidor           | `5000`                         |

## Ejecución

```bash
python app.py
```

La aplicación quedará disponible en `http://localhost:5000`.

## Estructura del proyecto

```
app.py                 Rutas HTTP y eventos de Socket.IO
extensions.py           Instancias compartidas (db, login_manager, socketio)
models.py               Modelos de datos (User, Post, Comment, Message)
forms.py                Formularios (Flask-WTF)
static/                 CSS, JS e imágenes subidas por los usuarios
templates/              Plantillas Jinja2
requirements.txt        Dependencias del proyecto
```

## Notas

- Las imágenes subidas se guardan en `static/uploads/` con un nombre único
  generado automáticamente; el límite de tamaño de subida es de 5 MB.
- El chat usa Socket.IO para mensajería en tiempo real y notifica el estado
  en línea/desconectado de los usuarios.

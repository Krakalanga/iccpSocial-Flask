import logging
import os
import re
from uuid import uuid4
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen
from urllib.error import URLError, HTTPError

from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify
)

from flask_socketio import emit, join_room, leave_room

from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user
)

from werkzeug.utils import secure_filename
from markupsafe import Markup, escape
from dotenv import load_dotenv

from extensions import db, login_manager, socketio
from models import User, Post, Message, Comment, Follow, Notification
from forms import (
    RegisterForm,
    LoginForm,
    PostForm,
    ProfileForm,
    MessageForm
)

# ==========================================
# Configuración
# ==========================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# La SECRET_KEY debe definirse mediante la variable de entorno SECRET_KEY
# en producción. El valor por defecto solo sirve para desarrollo local.
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    "dev-secret-key-change-me"
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(BASE_DIR, "database.db")
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["APP_TIMEZONE"] = os.environ.get("APP_TIMEZONE", "America/Santiago")

try:
    APP_TIMEZONE = ZoneInfo(app.config["APP_TIMEZONE"])
except ZoneInfoNotFoundError:
    logger.warning("Zona horaria inválida %s; usando UTC.", app.config["APP_TIMEZONE"])
    APP_TIMEZONE = timezone.utc

# Límite de tamaño de subida de archivos (5 MB)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp"
}


db.init_app(app)

login_manager.init_app(app)

socketio.init_app(
    app,
    cors_allowed_origins="*"
)


with app.app_context():
    db.create_all()


# ==========================================
# Funciones auxiliares
# ==========================================

def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def format_local_datetime(value, fmt="%d/%m/%Y · %H:%M"):
    """Formatea fechas guardadas en UTC usando la zona horaria de la app."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(APP_TIMEZONE).strftime(fmt)


app.add_template_filter(format_local_datetime, "localtime")


def wants_ajax_advancement():
    """True cuando una acción del navegador espera una respuesta JSON de logro."""
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def get_user_room(user_id):
    return f"user_{int(user_id)}"


def emit_chat_notification(message, sender, receiver, preview=None):
    text_preview = (preview or message.content or "Nuevo mensaje").strip()
    if len(text_preview) > 90:
        text_preview = text_preview[:87] + "..."

    socketio.emit(
        "chat_notification",
        {
            "message_id": message.id,
            "sender_id": sender.id,
            "sender": sender.username,
            "preview": text_preview,
            "avatar_url": url_for(
                "static",
                filename=f"uploads/{sender.profile_picture or 'default.png'}"
            ) + f"?v={sender.id}",
            "chat_url": url_for("chat", user_id=sender.id),
        },
        room=get_user_room(receiver.id),
    )


def ajax_advancement_response(message, category="success", redirect_url=None, success=True, status=200):
    payload = {
        "success": success,
        "message": message,
        "category": category,
        "redirect_url": redirect_url
    }
    return jsonify(payload), status


@app.template_filter("hashtags")
def linkify_hashtags(value):
    if not value:
        return ""
    escaped = str(escape(value))
    pattern = re.compile(r"(?<!\w)#([A-Za-z0-9_áéíóúÁÉÍÓÚñÑ]+)")
    return Markup(pattern.sub(lambda m: f'<a class="hashtag" href="{url_for("hashtag", tag=m.group(1))}">#{m.group(1)}</a>', escaped))


def save_image(file):
    """Guarda una imagen subida por el usuario y devuelve el nombre
    único generado, o None si el archivo no es válido."""

    if not file or file.filename == "":
        return None

    if not allowed_file(file.filename):
        logger.warning("Extensión de archivo no permitida: %s", file.filename)
        return None

    # Generar nombre único para evitar colisiones y sobrescrituras
    extension = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid4().hex}.{extension}"

    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    logger.info("Imagen guardada: %s", filename)
    return filename


# ==========================================
# Ruta para enviar mensajes con imagen
# ==========================================

@app.route("/send-image-message", methods=["POST"])
@login_required
def send_image_message():
    """Recibe un mensaje de chat que puede incluir contenido de texto,
    una imagen adjunta, o ambos, y lo emite en tiempo real por Socket.IO."""

    content = request.form.get("content", "").strip()
    sender_id = request.form.get("sender_id", type=int)
    receiver_id = request.form.get("receiver_id", type=int)

    if not sender_id or not receiver_id:
        return jsonify({"success": False, "error": "Faltan datos"}), 400

    # Solo se permite enviar mensajes en nombre del usuario autenticado
    if sender_id != current_user.id:
        return jsonify({"success": False, "error": "No autorizado"}), 403

    sender = db.session.get(User, sender_id)
    receiver = db.session.get(User, receiver_id)

    if not sender or not receiver:
        return jsonify({"success": False, "error": "Usuario no encontrado"}), 404

    image_name = None
    if "image" in request.files:
        image_file = request.files["image"]
        if image_file and allowed_file(image_file.filename):
            image_name = save_image(image_file)

    if not content and not image_name:
        return jsonify({"success": False, "error": "Mensaje vacío"}), 400

    message = Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        content=content if content else None,
        image=image_name
    )

    db.session.add(message)
    db.session.commit()

    room = get_room(sender.id, receiver.id)
    socketio.emit("receive_message", {
        "id": message.id,
        "sender_id": sender.id,
        "sender": sender.username,
        "content": message.content,
        "image": message.image,
        "timestamp": format_local_datetime(message.timestamp, "%H:%M")
    }, room=room)
    emit_chat_notification(message, sender, receiver, content or "Imagen")

    return jsonify({
        "success": True,
        "message_id": message.id,
        "image": message.image
    })


# ==========================================
# Inicio
# ==========================================

# ==========================================
# Registro
# ==========================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        if wants_ajax_advancement():
            return ajax_advancement_response("Ya tienes una sesión iniciada.", "info", url_for("home"))
        return redirect(url_for("home"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data.strip(), email=form.email.data.lower().strip())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        if wants_ajax_advancement():
            return ajax_advancement_response("Cuenta creada correctamente.", "success", url_for("login"))
        flash("Cuenta creada correctamente.", "success")
        return redirect(url_for("login"))

    if request.method == "POST" and wants_ajax_advancement():
        errors = [message for field_errors in form.errors.values() for message in field_errors]
        return ajax_advancement_response(errors[0] if errors else "No se pudo crear la cuenta.", "danger", None, False, 400)
    return render_template("register.html", form=form)

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if wants_ajax_advancement():
            return ajax_advancement_response("Ya tienes una sesión iniciada.", "info", url_for("home"))
        return redirect(url_for("home"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            user.is_online = True
            user.last_seen = datetime.utcnow()
            db.session.commit()
            login_user(user)
            next_page = request.args.get("next") or url_for("home")
            if wants_ajax_advancement():
                return ajax_advancement_response("Bienvenido.", "success", next_page)
            flash("Bienvenido.", "success")
            return redirect(next_page)

        if wants_ajax_advancement():
            return ajax_advancement_response("Correo o contraseña incorrectos.", "danger", None, False, 401)
        flash("Correo o contraseña incorrectos.", "danger")
    elif request.method == "POST" and wants_ajax_advancement():
        errors = [message for field_errors in form.errors.values() for message in field_errors]
        return ajax_advancement_response(errors[0] if errors else "Revisa los datos ingresados.", "danger", None, False, 400)
    return render_template("login.html", form=form)

@app.route("/logout")
@login_required
def logout():
    current_user.is_online = False
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    logout_user()
    if wants_ajax_advancement():
        return ajax_advancement_response("Has cerrado sesión correctamente.", "success", url_for("login"))
    flash("Has cerrado sesión correctamente.", "success")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    feed = request.args.get("feed", "for-you")
    query = Post.query

    if feed == "following":
        followed_ids = [row.followed_id for row in Follow.query.filter_by(follower_id=current_user.id).all()]
        if followed_ids:
            query = query.filter(Post.user_id.in_(followed_ids))
        else:
            query = query.filter(Post.id == -1)

    posts = query.order_by(Post.created_at.desc()).all()
    return render_template("home.html", posts=posts, feed=feed)


@app.route("/tag/<string:tag>")
@login_required
def hashtag(tag):
    clean_tag = re.sub(r"[^A-Za-z0-9_áéíóúÁÉÍÓÚñÑ]", "", tag)[:50]
    posts = Post.query.filter(Post.content.ilike(f"%#{clean_tag}%")).order_by(Post.created_at.desc()).all()
    return render_template("home.html", posts=posts, feed="tag", active_tag=clean_tag)


# ==========================================
# Crear publicación
# ==========================================

@app.route("/create-post", methods=["GET", "POST"])
@login_required
def create_post():
    form = PostForm()
    if form.validate_on_submit():
        image_name = save_image(form.image.data) if form.image.data else None
        post = Post(content=form.content.data.strip(), image=image_name, author=current_user)
        db.session.add(post)
        db.session.commit()
        if wants_ajax_advancement():
            return ajax_advancement_response("Publicación creada.", "success", url_for("home"))
        flash("Publicación creada.", "success")
        return redirect(url_for("home"))

    if request.method == "POST" and wants_ajax_advancement():
        errors = [message for field_errors in form.errors.values() for message in field_errors]
        return ajax_advancement_response(errors[0] if errors else "No se pudo crear la publicación.", "danger", None, False, 400)
    return render_template("create_post.html", form=form)

@app.route("/profile")
@login_required
def profile():
    posts = Post.query.filter_by(
        user_id=current_user.id
    ).order_by(
        Post.created_at.desc()
    ).all()

    return render_template(
        "profile.html", user=current_user, posts=posts,
        followers_count=Follow.query.filter_by(followed_id=current_user.id).count(),
        following_count=Follow.query.filter_by(follower_id=current_user.id).count(),
        is_following=False
    )


# ==========================================
# Perfil de otro usuario
# ==========================================

@app.route("/user/<int:user_id>")
@login_required
def user_profile(user_id):
    user = User.query.get_or_404(user_id)

    posts = Post.query.filter_by(
        user_id=user.id
    ).order_by(
        Post.created_at.desc()
    ).all()

    return render_template(
        "profile.html", user=user, posts=posts,
        followers_count=Follow.query.filter_by(followed_id=user.id).count(),
        following_count=Follow.query.filter_by(follower_id=user.id).count(),
        is_following=Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first() is not None
    )


# ==========================================
# Seguir / dejar de seguir
# ==========================================

@app.route("/user/<int:user_id>/followers")
@login_required
def followers_list(user_id):
    user = User.query.get_or_404(user_id)
    links = Follow.query.filter_by(followed_id=user.id).order_by(Follow.created_at.desc()).all()
    users = [link.follower for link in links]
    return render_template("connections.html", user=user, users=users, mode="followers")


@app.route("/user/<int:user_id>/following")
@login_required
def following_list(user_id):
    user = User.query.get_or_404(user_id)
    links = Follow.query.filter_by(follower_id=user.id).order_by(Follow.created_at.desc()).all()
    users = [link.followed for link in links]
    return render_template("connections.html", user=user, users=users, mode="following")



@app.route("/follow/<int:user_id>", methods=["POST"])
@login_required
def follow_user(user_id):
    user = User.query.get_or_404(user_id)
    redirect_url = request.referrer or url_for("user_profile", user_id=user.id)
    if user.id == current_user.id:
        if wants_ajax_advancement():
            return ajax_advancement_response("No puedes seguir tu propia cuenta.", "warning", redirect_url, False, 400)
        flash("No puedes seguir tu propia cuenta.", "warning")
        return redirect(redirect_url)

    existing = Follow.query.filter_by(follower_id=current_user.id, followed_id=user.id).first()
    if not existing:
        db.session.add(Follow(follower_id=current_user.id, followed_id=user.id))
        db.session.add(Notification(user_id=user.id, actor_id=current_user.id, kind="follow", text=f"@{current_user.username} comenzó a seguirte.", link=url_for("user_profile", user_id=current_user.id)))
        db.session.commit()
        message = f"Ahora sigues a @{user.username}."
    else:
        message = f"Ya sigues a @{user.username}."
    if wants_ajax_advancement():
        return ajax_advancement_response(message, "success", redirect_url)
    flash(message, "success")
    return redirect(redirect_url)

@app.route("/unfollow/<int:user_id>", methods=["POST"])
@login_required
def unfollow_user(user_id):
    user = User.query.get_or_404(user_id)
    redirect_url = request.referrer or url_for("user_profile", user_id=user.id)
    follow = Follow.query.filter_by(follower_id=current_user.id, followed_id=user_id).first()
    if follow:
        db.session.delete(follow)
        db.session.commit()
    message = f"Dejaste de seguir a @{user.username}."
    if wants_ajax_advancement():
        return ajax_advancement_response(message, "success", redirect_url)
    flash(message, "success")
    return redirect(redirect_url)

@app.route("/notifications")
@login_required
def notifications():
    items = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(60).all()
    unread_messages = Message.query.filter_by(receiver_id=current_user.id, read=False).count()
    return render_template("notifications.html", notifications=items, unread_messages=unread_messages)


@app.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    redirect_url = url_for("notifications")
    if wants_ajax_advancement():
        return ajax_advancement_response("Notificaciones marcadas como leídas.", "success", redirect_url)
    flash("Notificaciones marcadas como leídas.", "success")
    return redirect(redirect_url)

@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
    form = ProfileForm()
    if form.validate_on_submit():
        current_user.username = form.username.data.strip()
        current_user.bio = form.bio.data.strip()
        file = request.files.get("profile_picture")
        message = "Perfil actualizado correctamente."
        category = "success"

        if file and file.filename != "":
            if allowed_file(file.filename):
                if current_user.profile_picture and current_user.profile_picture != "default.png":
                    old_path = os.path.join(app.config["UPLOAD_FOLDER"], current_user.profile_picture)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                image_name = save_image(file)
                if image_name:
                    current_user.profile_picture = image_name
                    message = "Foto de perfil actualizada correctamente."
                else:
                    message, category = "Error al guardar la imagen.", "danger"
            else:
                message, category = "Formato no permitido. Usa JPG, PNG, GIF o WEBP.", "danger"

        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception("Error al guardar los cambios de perfil")
            message, category = "Error al guardar los cambios.", "danger"

        if wants_ajax_advancement():
            ok = category == "success"
            return ajax_advancement_response(message, category, url_for("profile") if ok else None, ok, 200 if ok else 400)
        flash(message, category)
        return redirect(url_for("profile"))

    if request.method == "POST":
        errors = [f"Error en {field}: {error}" for field, field_errors in form.errors.items() for error in field_errors]
        if wants_ajax_advancement():
            return ajax_advancement_response(errors[0] if errors else "Revisa los datos del perfil.", "danger", None, False, 400)
        for error in errors:
            flash(error, "danger")

    if request.method == "GET":
        form.username.data = current_user.username
        form.bio.data = current_user.bio
    return render_template("edit_profile.html", form=form)

@app.route("/delete-post/<int:post_id>")
@login_required
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    if post.author != current_user:
        redirect_url = url_for("home")
        if wants_ajax_advancement():
            return ajax_advancement_response("No tienes permiso para eliminar esta publicación.", "danger", redirect_url, False, 403)
        flash("No tienes permiso para eliminar esta publicación.", "danger")
        return redirect(redirect_url)

    if post.image:
        image_path = os.path.join(app.config["UPLOAD_FOLDER"], post.image)
        if os.path.exists(image_path):
            os.remove(image_path)
    db.session.delete(post)
    db.session.commit()
    redirect_url = url_for("profile")
    if wants_ajax_advancement():
        return ajax_advancement_response("Publicación eliminada.", "success", redirect_url)
    flash("Publicación eliminada.", "success")
    return redirect(redirect_url)

@app.route("/chat/<int:user_id>", methods=["GET", "POST"])
@login_required
def chat(user_id):
    other_user = User.query.get_or_404(user_id)
    form = MessageForm()

    if form.validate_on_submit():
        content = form.content.data.strip()
        
        if content or request.files.get('image'):
            message = Message(
                sender=current_user,
                receiver=other_user,
                content=content if content else None
            )
            
            if 'image' in request.files:
                image_file = request.files['image']
                if image_file and allowed_file(image_file.filename):
                    image_name = save_image(image_file)
                    if image_name:
                        message.image = image_name
            
            db.session.add(message)
            db.session.commit()
            emit_chat_notification(
                message,
                current_user,
                other_user,
                content or ("Imagen" if message.image else "Nuevo mensaje")
            )

        return redirect(url_for("chat", user_id=other_user.id))

    messages = Message.query.filter(
        (
            (Message.sender_id == current_user.id) &
            (Message.receiver_id == other_user.id)
        ) |
        (
            (Message.sender_id == other_user.id) &
            (Message.receiver_id == current_user.id)
        )
    ).order_by(
        Message.timestamp.asc()
    ).all()

    for msg in messages:
        if msg.receiver_id == current_user.id and not msg.read:
            msg.read = True

    db.session.commit()

    return render_template(
        "chat.html",
        form=form,
        messages=messages,
        other_user=other_user
    )


# ==========================================
# GIPHY: búsqueda y envío seguro de GIFs
# ==========================================

GIPHY_API_BASE = "https://api.giphy.com/v1/gifs"
GIPHY_ALLOWED_HOSTS = {"media.giphy.com", "media0.giphy.com", "media1.giphy.com", "media2.giphy.com", "media3.giphy.com", "media4.giphy.com"}


def _giphy_request(endpoint, **params):
    api_key = os.environ.get("GIPHY_API_KEY", "").strip()
    if not api_key:
        return None, "GIPHY no está configurado. Define GIPHY_API_KEY en el entorno."

    query = {"api_key": api_key, "limit": 18, "rating": "pg", "lang": "es", **params}
    url = f"{GIPHY_API_BASE}/{endpoint}?{urlencode(query)}"
    try:
        with urlopen(url, timeout=6) as response:
            payload = __import__("json").loads(response.read().decode("utf-8"))
    except (URLError, HTTPError, TimeoutError, ValueError) as exc:
        logger.warning("Error consultando GIPHY: %s", exc)
        return None, "No pudimos cargar GIFs en este momento."

    results = []
    for item in payload.get("data", []):
        images = item.get("images", {})
        preview = (images.get("fixed_width") or images.get("downsized") or {}).get("url")
        original = (images.get("original") or {}).get("url")
        if preview and original:
            results.append({
                "id": item.get("id"),
                "title": item.get("title") or "GIF",
                "preview_url": preview,
                "url": original,
            })
    return results, None


def _valid_giphy_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname in GIPHY_ALLOWED_HOSTS and parsed.path.lower().endswith((".gif", ".webp"))


@app.route("/api/giphy")
@login_required
def giphy_search():
    query = request.args.get("q", "").strip()[:80]
    endpoint = "search" if query else "trending"
    params = {"q": query} if query else {}
    results, error = _giphy_request(endpoint, **params)
    if error:
        status = 503 if "configurado" not in error else 501
        return jsonify({"success": False, "error": error, "results": []}), status
    return jsonify({"success": True, "results": results})


@app.route("/chat/<int:user_id>/gif", methods=["POST"])
@login_required
def send_gif(user_id):
    other_user = User.query.get_or_404(user_id)
    gif_url = request.form.get("gif_url", "").strip()
    if not _valid_giphy_url(gif_url):
        return jsonify({"success": False, "error": "GIF de GIPHY no válido."}), 400

    message = Message(sender=current_user, receiver=other_user, image=gif_url)
    db.session.add(message)
    db.session.commit()
    room = get_room(current_user.id, other_user.id)
    payload = {
        "id": message.id, "sender_id": current_user.id, "sender": current_user.username,
        "content": None, "image": gif_url, "timestamp": format_local_datetime(message.timestamp, "%H:%M")
    }
    socketio.emit("receive_message", payload, room=room)
    emit_chat_notification(message, current_user, other_user, "GIF")
    return jsonify({"success": True, "message": payload})


# ==========================================
# Lista de conversaciones
# ==========================================

@app.route("/messages")
@login_required
def conversations():
    users = User.query.filter(
        User.id != current_user.id
    ).order_by(
        User.username.asc()
    ).all()

    return render_template("messages.html", users=users)


# ==========================================
# Agregar comentario
# ==========================================

@app.route("/comment/<int:post_id>", methods=["POST"])
@login_required
def add_comment(post_id):
    post = Post.query.get_or_404(post_id)
    content = request.form.get("content", "").strip()
    redirect_url = request.referrer or (url_for("home") + f"#post-{post.id}")
    if not content:
        if wants_ajax_advancement():
            return ajax_advancement_response("Escribe un comentario antes de enviarlo.", "warning", None, False, 400)
        flash("Escribe un comentario antes de enviarlo.", "warning")
        return redirect(redirect_url)

    comment = Comment(content=content, user_id=current_user.id, post_id=post.id)
    db.session.add(comment)
    if post.user_id != current_user.id:
        db.session.add(Notification(user_id=post.user_id, actor_id=current_user.id, kind="comment", text=f"@{current_user.username} comentó tu publicación.", link=url_for("home") + f"#post-{post.id}"))
    db.session.commit()
    if wants_ajax_advancement():
        return ajax_advancement_response("Comentario publicado.", "success", redirect_url)
    flash("Comentario publicado.", "success")
    return redirect(redirect_url)

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404


# ==========================================
# Página 403
# ==========================================

@app.errorhandler(403)
def forbidden(error):
    return render_template("403.html"), 403


# ==========================================
# Archivo demasiado grande
# ==========================================

@app.errorhandler(413)
def file_too_large(error):
    max_mb = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
    message = f"El archivo es demasiado grande. El tamaño máximo permitido es {max_mb} MB."
    if wants_ajax_advancement():
        return ajax_advancement_response(message, "danger", None, False, 413)
    flash(message, "danger")
    return redirect(request.referrer or url_for("home"))

@app.context_processor
def inject_user():
    unread_notifications = 0
    unread_messages = 0
    if current_user.is_authenticated:
        unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        unread_messages = Message.query.filter_by(receiver_id=current_user.id, read=False).count()
    return dict(
        current_user=current_user,
        unread_notifications=unread_notifications,
        unread_messages=unread_messages
    )


# ==========================================
# SOCKET.IO
# ==========================================

def get_room(user1, user2):
    ids = sorted([user1, user2])
    return f"chat_{ids[0]}_{ids[1]}"


@socketio.on("connect")
def handle_connect():
    if current_user.is_authenticated:
        join_room(get_user_room(current_user.id))
        # ✅ USAR s_online
        current_user.is_online = True
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        emit("user_status", {
            "user_id": current_user.id,
            "is_online": True,
            "username": current_user.username
        }, broadcast=True)


@socketio.on("disconnect")
def handle_disconnect():
    if current_user.is_authenticated:
        # ✅ USAR s_online
        current_user.is_online = False
        current_user.last_seen = datetime.utcnow()
        db.session.commit()
        
        emit("user_status", {
            "user_id": current_user.id,
            "is_online": False,
            "username": current_user.username
        }, broadcast=True)


@socketio.on("join")
def handle_join(data):
    if not current_user.is_authenticated:
        return
    receiver_id = int(data.get("receiver_id", 0))
    room = get_room(current_user.id, receiver_id)
    join_room(room)

    other_user = db.session.get(User, receiver_id)
    if other_user:
        emit("user_status", {
            "user_id": other_user.id,
            "is_online": other_user.is_online,  # ✅ USAR s_online
            "username": other_user.username
        }, room=room)


@socketio.on("leave")
def handle_leave(data):
    if not current_user.is_authenticated:
        return
    receiver_id = int(data.get("receiver_id", 0))
    leave_room(get_room(current_user.id, receiver_id))


@socketio.on("typing")
def handle_typing(data):
    if not current_user.is_authenticated:
        return
    receiver_id = int(data.get("receiver_id", 0))
    room = get_room(current_user.id, receiver_id)
    emit(
        "typing",
        {
            "username": current_user.username,
            "sender_id": current_user.id
        },
        room=room,
        include_self=False
    )


@socketio.on("send_message")
def handle_message(data):
    if not current_user.is_authenticated:
        return
    receiver = db.session.get(User, int(data.get("receiver_id", 0)))
    content = str(data.get("content", "")).strip()[:500]
    if not receiver or not content:
        return

    sender = current_user
    message = Message(
        sender_id=sender.id,
        receiver_id=receiver.id,
        content=content
    )

    db.session.add(message)
    db.session.commit()

    room = get_room(sender.id, receiver.id)

    emit(
        "receive_message",
        {
            "sender_id": sender.id,
            "sender": sender.username,
            "content": message.content,
            "timestamp": format_local_datetime(message.timestamp, "%H:%M")
        },
        room=room
    )
    emit_chat_notification(message, sender, receiver, message.content)


@socketio.on("user_connected")
def handle_user_connected(data=None):
    if not current_user.is_authenticated:
        return
    current_user.is_online = True
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    emit("user_status", {
        "user_id": current_user.id, "is_online": True, "username": current_user.username
    }, broadcast=True)


@socketio.on("user_disconnected")
def handle_user_disconnected(data=None):
    if not current_user.is_authenticated:
        return
    current_user.is_online = False
    current_user.last_seen = datetime.utcnow()
    db.session.commit()
    emit("user_status", {
        "user_id": current_user.id, "is_online": False, "username": current_user.username
    }, broadcast=True)


@socketio.on("get_all_status")
def handle_get_all_status():
    users = User.query.all()
    for user in users:
        emit("user_status", {
            "user_id": user.id,
            "is_online": user.is_online,  # ✅ USAR s_online
            "username": user.username
        })


# ==========================================
# Ejecutar aplicación
# ==========================================

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_DEBUG", "1") == "1"

    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=debug_mode
    )
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db, login_manager


@login_manager.user_loader
def load_user(user_id):

    return db.session.get(
        User,
        int(user_id)
    )



class User(UserMixin, db.Model):

    __tablename__ = "users"


    id = db.Column(
        db.Integer,
        primary_key=True
    )

    is_online = db.Column(db.Boolean, default=False)  
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)

    username = db.Column(
        db.String(30),
        unique=True,
        nullable=False
    )


    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )


    password_hash = db.Column(
        db.String(255),
        nullable=False
    )


    bio = db.Column(
        db.String(250),
        default=""
    )


    profile_picture = db.Column(
        db.String(255),
        nullable=False,
        default="default.png"
    )


    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )



    # -------------------------
    # Relaciones
    # -------------------------


    posts = db.relationship(
        "Post",
        back_populates="author",
        lazy="select",
        cascade="all, delete-orphan"
    )


    comments = db.relationship(
        "Comment",
        back_populates="author",
        lazy="select",
        cascade="all, delete-orphan"
    )


    sent_messages = db.relationship(
        "Message",
        foreign_keys="Message.sender_id",
        back_populates="sender",
        lazy="select",
        cascade="all, delete-orphan"
    )


    received_messages = db.relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        back_populates="receiver",
        lazy="select",
        cascade="all, delete-orphan"
    )



    # -------------------------
    # Password
    # -------------------------


    def set_password(self, password):

        self.password_hash = generate_password_hash(
            password
        )



    def check_password(self, password):

        return check_password_hash(
            self.password_hash,
            password
        )



    def __repr__(self):

        return f"<User {self.username}>"





class Post(db.Model):

    __tablename__ = "posts"


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    content = db.Column(
        db.Text,
        nullable=False
    )


    image = db.Column(
        db.String(255),
        nullable=True
    )


    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )



    author = db.relationship(
        "User",
        back_populates="posts"
    )



    comments = db.relationship(
        "Comment",
        back_populates="post",
        lazy="selectin",
        cascade="all, delete-orphan"
    )



    def __repr__(self):

        return f"<Post {self.id}>"







class Comment(db.Model):

    __tablename__ = "comments"



    id = db.Column(
        db.Integer,
        primary_key=True
    )


    content = db.Column(
        db.String(500),
        nullable=False
    )


    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )



    user_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )



    post_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "posts.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )



    author = db.relationship(
        "User",
        back_populates="comments"
    )



    post = db.relationship(
        "Post",
        back_populates="comments"
    )



    def __repr__(self):

        return f"<Comment {self.id}>"







class Message(db.Model):

    __tablename__ = "messages"



    id = db.Column(
        db.Integer,
        primary_key=True
    )



    sender_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )



    receiver_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )



    # Puede ser nulo cuando el mensaje solo contiene una imagen
    content = db.Column(
        db.Text,
        nullable=True
    )



    # Nombre del archivo de imagen adjunta (opcional)
    image = db.Column(
        db.String(255),
        nullable=True
    )



    timestamp = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )



    read = db.Column(
        db.Boolean,
        default=False
    )



    sender = db.relationship(
        "User",
        foreign_keys=[sender_id],
        back_populates="sent_messages"
    )



    receiver = db.relationship(
        "User",
        foreign_keys=[receiver_id],
        back_populates="received_messages"
    )



    def __repr__(self):

        return f"<Message {self.id}>"

class Follow(db.Model):
    __tablename__ = "follows"
    __table_args__ = (db.UniqueConstraint("follower_id", "followed_id", name="uq_follow_pair"),)

    id = db.Column(db.Integer, primary_key=True)
    follower_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    follower = db.relationship("User", foreign_keys=[follower_id], backref=db.backref("following_links", cascade="all, delete-orphan"))
    followed = db.relationship("User", foreign_keys=[followed_id], backref=db.backref("follower_links", cascade="all, delete-orphan"))


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    kind = db.Column(db.String(30), nullable=False)
    text = db.Column(db.String(180), nullable=False)
    link = db.Column(db.String(255), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", foreign_keys=[user_id], backref=db.backref("notifications", cascade="all, delete-orphan"))
    actor = db.relationship("User", foreign_keys=[actor_id])

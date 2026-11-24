# forms.py
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, PasswordField, EmailField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, Optional

# ==========================================
# Formulario de registro
# ==========================================

class RegisterForm(FlaskForm):
    username = StringField(
        'Nombre de usuario',
        validators=[
            DataRequired(message='El nombre de usuario es obligatorio'),
            Length(min=3, max=80, message='El nombre debe tener entre 3 y 80 caracteres')
        ]
    )
    
    email = EmailField(
        'Correo electrónico',
        validators=[
            DataRequired(message='El correo es obligatorio'),
            Email(message='Ingresa un correo válido')
        ]
    )
    
    password = PasswordField(
        'Contraseña',
        validators=[
            DataRequired(message='La contraseña es obligatoria'),
            Length(min=8, message='La contraseña debe tener al menos 8 caracteres')
        ]
    )
    
    confirm_password = PasswordField(
        'Confirmar contraseña',
        validators=[
            DataRequired(message='Confirma tu contraseña'),
            EqualTo('password', message='Las contraseñas no coinciden')
        ]
    )
    
    submit = SubmitField('Registrarse')


# ==========================================
# Formulario de login
# ==========================================

class LoginForm(FlaskForm):
    email = EmailField(
        'Correo electrónico',
        validators=[
            DataRequired(message='El correo es obligatorio'),
            Email(message='Ingresa un correo válido')
        ]
    )
    
    password = PasswordField(
        'Contraseña',
        validators=[
            DataRequired(message='La contraseña es obligatoria')
        ]
    )
    
    submit = SubmitField('Iniciar sesión')  # ✅ AGREGADO


# ==========================================
# Formulario para publicaciones
# ==========================================

class PostForm(FlaskForm):
    content = TextAreaField(
        'Contenido',
        validators=[
            DataRequired(message='El contenido es obligatorio'),
            Length(max=1000, message='El contenido no puede exceder los 1000 caracteres')
        ]
    )
    
    image = FileField(
        'Imagen',
        validators=[
            Optional(),
            FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Solo imágenes permitidas')
        ]
    )
    
    submit = SubmitField('Publicar')


# ==========================================
# Formulario para editar perfil
# ==========================================

class ProfileForm(FlaskForm):
    username = StringField(
        'Nombre de usuario',
        validators=[
            DataRequired(message='El nombre de usuario es obligatorio'),
            Length(min=3, max=80, message='El nombre debe tener entre 3 y 80 caracteres')
        ]
    )
    
    bio = TextAreaField(
        'Biografía',
        validators=[
            Optional(),
            Length(max=500, message='La biografía no puede exceder los 500 caracteres')
        ]
    )
    
    profile_picture = FileField(
        'Foto de perfil',
        validators=[
            Optional(),
            FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Solo imágenes permitidas')
        ]
    )
    
    submit = SubmitField('Guardar cambios')


# ==========================================
# Formulario para mensajes
# ==========================================

class MessageForm(FlaskForm):
    content = TextAreaField(
        'Mensaje',
        validators=[
            Optional(),
            Length(max=500, message='El mensaje no puede exceder los 500 caracteres')
        ]
    )
    
    image = FileField(
        'Imagen',
        validators=[
            Optional(),
            FileAllowed(['jpg', 'jpeg', 'png', 'gif', 'webp'], 'Solo imágenes permitidas')
        ]
    )
    
    submit = SubmitField('Enviar')
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    
    # NUEVA COLUMNA DE JERARQUÍA
    rol = db.Column(db.String(20), default='empleado', nullable=False)

    # Función para crear la contraseña encriptada
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    # Función para verificar si la contraseña es correcta
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Función de ayuda para saber rápido si es el jefe
    def is_admin(self):
        return self.rol == 'admin'

    def __repr__(self):
        return f'<User {self.username} - Rol: {self.rol}>'
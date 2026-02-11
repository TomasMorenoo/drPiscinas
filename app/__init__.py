from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect # <--- 1. ANTI-HACKEO FORMULARIOS
from flask_limiter import Limiter      # <--- 2. LIMITADOR DE TRÁFICO
from flask_limiter.util import get_remote_address
from datetime import timedelta         # <--- 3. PARA EL TIEMPO DE SESIÓN
from dotenv import load_dotenv
import os

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Configuración del Limitador (Acepta aprox 100 usuarios activos dándole caña)
# "200 per minute" significa que una sola persona no puede hacer más de 3 clicks por segundo constante.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"] 
)

def create_app():
    load_dotenv()

    app = Flask(__name__)

    # --- CONFIGURACIÓN DE BASE DE DATOS ---
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # --- CONFIGURACIÓN DE SEGURIDAD (CRÍTICO) ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    
    # 1. Cookies Blindadas (Solo viajan por HTTPS y JS no las toca)
    app.config["SESSION_COOKIE_SECURE"] = True 
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'
    
    # 2. Timeout de 1 Hora (Si no tocás nada, te saca)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)

    # --- INICIALIZAR EXTENSIONES ---
    db.init_app(app)
    
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sesión expirada o acceso denegado."
    login_manager.login_message_category = "warning"

    csrf.init_app(app)    # Activamos escudo en formularios
    limiter.init_app(app) # Activamos escudo de tráfico

    # --- IMPORTAR RUTAS ---
    from app.routers.main_router import main_bp
    from app.routers.country_router import country_bp    
    from app.routers.barrio_router import barrio_bp
    from app.routers.casa_router import casa_bp
    from app.routers.products_router import product_bp
    from app.routers.visit_router import visit_bp
    from app.routers.promo_router import promo_bp
    from app.routers.dashboard_router import dashboard_bp
    from app.routers.auth_router import auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(barrio_bp)
    app.register_blueprint(casa_bp)   
    app.register_blueprint(product_bp)  
    app.register_blueprint(visit_bp)     
    app.register_blueprint(promo_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)

    return app

from app.models.user import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
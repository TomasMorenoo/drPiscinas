from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect 
from flask_limiter import Limiter 
from flask_limiter.util import get_remote_address
from datetime import timedelta 
from dotenv import load_dotenv
import os

# Inicialización de extensiones
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

# Limitador de tráfico (Máximo 200 pedidos por minuto por IP)
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
    
    # --- CONFIGURACIÓN DE SEGURIDAD ---
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
    
    # 1. Sesión Volátil: Al cerrar el navegador/pestaña se elimina la sesión
    app.config['SESSION_PERMANENT'] = False 
    
    # 2. Timeout de inactividad: 1 Hora (mientras el navegador esté abierto)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)
    
    # 3. Cookies Blindadas (Solo viajan por HTTPS y son invisibles para JS)
    app.config["SESSION_COOKIE_SECURE"] = True 
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'

    # --- INICIALIZAR EXTENSIONES ---
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sesión expirada o acceso denegado."
    login_manager.login_message_category = "warning"

    # --- MANEJADORES DE ERROR ---
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # --- REGISTRO DE BLUEPRINTS ---
    from app.routers.main_router import main_bp
    from app.routers.country_router import country_bp    
    from app.routers.barrio_router import barrio_bp
    from app.routers.casa_router import casa_bp
    from app.routers.products_router import product_bp
    from app.routers.visit_router import visit_bp
    from app.routers.promo_router import promo_bp
    from app.routers.dashboard_router import dashboard_bp
    from app.routers.auth_router import auth_bp
    from app.models.abono_historico import AbonoHistorico
    from app.routers.user_router import user_bp
    from app.routers.grupo_router import grupo_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(barrio_bp)
    app.register_blueprint(casa_bp)   
    app.register_blueprint(product_bp)  
    app.register_blueprint(visit_bp)     
    app.register_blueprint(promo_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(grupo_bp)

    # ========================================================
    # NUEVO: Inyectar variable global para el botón de borrado
    # ========================================================
    @app.context_processor
    def inyectar_variables():
        # Si existe este archivo, borrado_activado será True
        return dict(borrado_activado=os.path.exists("borrado_activado.flag"))

    return app

# Carga de usuario
from app.models.user import User
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
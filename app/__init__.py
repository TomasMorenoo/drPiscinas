import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect  # <--- Agregado
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect() # <--- Agregado
limiter = Limiter(key_func=get_remote_address, default_limits=["5000 per day", "500 per hour"])

def create_app():
    app = Flask(__name__)
    
    # --- LÓGICA DE CONEXIÓN UNIVERSAL ---
    database_url = os.getenv("DATABASE_URL")
    
    if not database_url:
        user = os.getenv("DB_USER") or os.getenv("POSTGRES_USER")
        pw = os.getenv("DB_PASS") or os.getenv("POSTGRES_PASSWORD")
        host = os.getenv("DB_HOST", "db")
        name = os.getenv("DB_NAME") or os.getenv("POSTGRES_DB")
        database_url = f"postgresql://{user}:{pw}@{host}:5432/{name}"

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key-drpiscinas-2024")

    # Inicializar extensiones
    db.init_app(app)
    login_manager.init_app(app)
    limiter.init_app(app)
    csrf.init_app(app) # <--- Agregado
    login_manager.login_view = "auth.login"

    # --- REGISTRO DE BLUEPRINTS ---
    from app.routers.auth_router import auth_bp
    from app.routers.main_router import main_bp
    from app.routers.user_router import user_bp
    from app.routers.country_router import country_bp
    from app.routers.barrio_router import barrio_bp
    from app.routers.casa_router import casa_bp
    from app.routers.products_router import product_bp
    from app.routers.promo_router import promo_bp
    from app.routers.visit_router import visit_bp
    from app.routers.dashboard_router import dashboard_bp
    from app.routers.grupo_router import grupo_bp
    from app.routers.estadisticas_router import estadisticas_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(barrio_bp)
    app.register_blueprint(casa_bp)
    app.register_blueprint(product_bp)
    app.register_blueprint(visit_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(promo_bp)
    app.register_blueprint(grupo_bp)
    app.register_blueprint(estadisticas_bp)

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(int(user_id))
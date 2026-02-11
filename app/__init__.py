from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager # <--- IMPORTAR
from dotenv import load_dotenv
import os

db = SQLAlchemy()
login_manager = LoginManager() # <--- INICIALIZAR GLOBALMENTE

def create_app():
    load_dotenv()

    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    db.init_app(app)
    
    # --- CONFIGURACIÓN DE LOGIN ---
    login_manager.init_app(app)
    login_manager.login_view = "auth.login" # Si intentan entrar sin permiso, van acá
    login_manager.login_message = "Debes iniciar sesión para ver esta página."
    login_manager.login_message_category = "warning"

    # importar rutas
    from app.routers.main_router import main_bp
    from app.routers.country_router import country_bp    
    from app.routers.barrio_router import barrio_bp
    from app.routers.casa_router import casa_bp
    from app.routers.products_router import product_bp
    from app.routers.visit_router import visit_bp
    from app.routers.promo_router import promo_bp
    from app.routers.dashboard_router import dashboard_bp
    from app.routers.auth_router import auth_bp # <--- NUEVO ROUTER DE AUTH

    app.register_blueprint(main_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(barrio_bp)
    app.register_blueprint(casa_bp)   
    app.register_blueprint(product_bp)  
    app.register_blueprint(visit_bp)     
    app.register_blueprint(promo_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(auth_bp) # <--- REGISTRAR AUTH

    return app

# --- CARGADOR DE USUARIO (NECESARIO PARA FLASK-LOGIN) ---
# Esto permite que Flask busque al usuario en la DB por su ID
from app.models.user import User

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
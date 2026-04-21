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
    from app.routers.root_router import root_bp
    from app.routers.config_router import config_bp

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
    app.register_blueprint(root_bp)
    app.register_blueprint(config_bp)

    # --- FILTRO JINJA2: formato pesos argentinos (punto como separador de miles) ---
    @app.template_filter('pesos')
    def format_pesos(value):
        try:
            return "{:,.0f}".format(float(value)).replace(',', '.')
        except (ValueError, TypeError):
            return value

    # --- CONTEXT PROCESSOR: cfg global (disponible en todos los templates) ---
    @app.context_processor
    def inject_cfg():
        from types import SimpleNamespace
        from app.models.configuracion import Configuracion

        try:
            # Icono de la app (estático)
            icon_path = os.path.join(app.static_folder, 'drpiscina-192.png')
            app_icon_192 = os.path.exists(icon_path)

            # Imagen de fondo del login (subida por root)
            login_filename = Configuracion.get('login_image_filename', None)
            if login_filename:
                img_path = os.path.join(app.static_folder, 'uploads', login_filename)
                login_image = os.path.exists(img_path)
            else:
                login_image = False

            app_name        = Configuracion.get('app_name', 'Dr. Piscinas')
            app_description = Configuracion.get('app_description', 'Sistema de gestión de piletas')
            footer_texto    = Configuracion.get('footer_texto', '')
            footer_contacto = Configuracion.get('footer_contacto', '')
        except Exception:
            app_icon_192    = False
            login_image     = False
            app_name        = 'Dr. Piscinas'
            app_description = 'Sistema de gestión de piletas'
            footer_texto    = ''
            footer_contacto = ''

        cfg = SimpleNamespace(
            app_name=app_name,
            app_description=app_description,
            app_icon_192=app_icon_192,
            login_image=login_image,
            footer_texto=footer_texto,
            footer_contacto=footer_contacto,
        )
        from datetime import datetime
        return dict(cfg=cfg, now=datetime.now())

    # --- MODO MANTENIMIENTO ---
    @app.before_request
    def check_maintenance_mode():
        import os
        from flask import request, render_template
        from flask_login import current_user
        
        # Si existe el archivo bandera, estamos en mantenimiento
        if os.path.exists('mantenimiento.flag'):
            
            # 1. Dejar cargar los archivos visuales (imágenes, CSS)
            if request.path.startswith('/static/'):
                return None
            
            # 2. Rutas que siempre deben pasar (acceso oculto + recursos visuales)
            PASS_PATHS = ('/acceso', '/root/icon/192', '/root/login-image')
            if request.path in PASS_PATHS:
                return None
            
            # 3. Dejar pasar si el usuario está logueado y es 'root' 
            # (Si tu usuario principal se llama distinto, cambialo acá)
            if current_user.is_authenticated and current_user.username == 'root':
                return None
            
            # 4. A todos los demás, bloquearlos y mostrar la pantalla de pausa
            return render_template('errors/mantenimiento.html'), 503

    return app

@login_manager.user_loader
def load_user(user_id):
    from app.models.user import User
    return User.query.get(int(user_id))
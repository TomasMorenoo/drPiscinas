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

# --- CONFIGURACIÓN DE BASE DE DATOS FINAL ---
    app.config["SQLALCHEMY_DATABASE_URI"] = "postgresql://drPiscinas:administrador@127.0.0.1:5433/drPiscinas_db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    print("🚀 CONECTADO EXITOSAMENTE AL DOCKER DE DR PISCINAS")
    
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
    # --- Crear Tablas ---
    
    with app.app_context():
        from sqlalchemy import text
        print("🔍 Verificando estructura de base de datos...")
        
        # 1. Crea las tablas nuevas (como 'grupos_clientes' y 'cierres_mes') si no existen
        db.create_all()
        
        # 2. Inyecta columnas nuevas en tablas viejas (Migración automática simple)
        try:
            # Agregamos grupo_id a la tabla casas si no existe
            # Usamos el nombre de la tabla 'casas' que es el que definiste en el modelo
            db.session.execute(text("ALTER TABLE casas ADD COLUMN IF NOT EXISTS grupo_id INTEGER;"))
            
            # Intentamos crear la relación (FK)
            try:
                db.session.execute(text("""
                    ALTER TABLE casas 
                    ADD CONSTRAINT fk_casa_grupo 
                    FOREIGN KEY (grupo_id) 
                    REFERENCES grupos_clientes(id);
                """))
            except Exception:
                pass # Si ya existe el constraint, no pasa nada
                
            db.session.commit()
            print("✅ Estructura de base de datos actualizada.")
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Nota: No se pudo alterar la tabla (probablemente ya está actualizada).")

        # ========================================================
        # NUEVO: MIGRACIÓN DEL CANDADO DE MESES CERRADOS
        # Convierte los registros viejos al nuevo sistema seguro
        # ========================================================
        try:
            from app.models.abono_historico import AbonoHistorico
            from app.models.cierre_mes import CierreMes
            meses_hist = db.session.query(AbonoHistorico.mes, AbonoHistorico.anio).distinct().all()
            for m, a in meses_hist:
                if not CierreMes.query.filter_by(mes=m, anio=a).first():
                    db.session.add(CierreMes(mes=m, anio=a))
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"⚠️ Nota: Error al migrar CierreMes: {e}")

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
    # Inyectar variable global para el botón de borrado
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
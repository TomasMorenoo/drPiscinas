from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os

db = SQLAlchemy()

def create_app():
    load_dotenv()

    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

    db.init_app(app)

    # importar rutas
    from app.routers.main_router import main_bp
    from app.routers.country_router import country_bp   
    from app.routers.barrio_router import barrio_bp
    from app.routers.casa_router import casa_bp
    from app.routers.products_router import product_bp
    from app.routers.visit_router import visit_bp
    from app.routers.promo_router import promo_bp
    
    

    app.register_blueprint(main_bp)
    app.register_blueprint(country_bp)
    app.register_blueprint(barrio_bp)
    app.register_blueprint(casa_bp)   
    app.register_blueprint(product_bp)  
    app.register_blueprint(visit_bp)     
    app.register_blueprint(promo_bp)

    return app

from app import create_app, db

# IMPORTANTE: Al importar 'app.models', Python corre tu __init__.py
# y SQLAlchemy "descubre" todas tus tablas (Country, Barrio, etc.) de una sola vez.
import app.models 

app = create_app()

if __name__ == '__main__':
    with app.app_context():
        # Como ya importamos app.models arriba, create_all() ya sabe qué tablas crear.
        db.create_all()
        print("✅ Base de datos verificada. Tablas listas.")

    # Arrancamos la web para que escuche a todo el mundo (0.0.0.0)
    app.run(host='0.0.0.0', port=5000, debug=True)
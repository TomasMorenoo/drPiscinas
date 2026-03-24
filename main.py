from app import create_app, db
import app.models 

app = create_app()

if __name__ == '__main__':
    # Eliminamos el create_all de acá para que no cree bases SQLite accidentales
    app.run(host='0.0.0.0', port=5000, debug=True)
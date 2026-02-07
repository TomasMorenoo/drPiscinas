from app import create_app

app = create_app()

if __name__ == '__main__':
    # El 0.0.0.0 es la clave: significa "escuchar en todas las direcciones"
    app.run(host='0.0.0.0', port=5000, debug=True)
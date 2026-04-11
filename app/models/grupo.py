from app import db

class GrupoCliente(db.Model):
    __tablename__ = 'grupos_clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)          # Usado en mensaje de WhatsApp
    nombre_identificador = db.Column(db.String(100), nullable=True)  # Mostrado en dashboard y planilla

    @property
    def nombre_display(self):
        """Devuelve el nombre de pantalla: nombre_identificador si existe, sino nombre."""
        return self.nombre_identificador or self.nombre

    # La relación inversa se define desde Casa
    def __repr__(self):
        return f"<GrupoCliente {self.nombre}>"
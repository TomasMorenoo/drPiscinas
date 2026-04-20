from app import db

class GrupoCliente(db.Model):
    __tablename__ = 'grupos_clientes'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)          # Usado en mensaje de WhatsApp
    nombre_identificador = db.Column(db.String(100), nullable=True)  # Mostrado en dashboard y planilla
    saldo_a_favor = db.Column(db.Numeric(10, 2), nullable=False, default=0.0)
    saldo_desde_mes = db.Column(db.Integer, nullable=True)   # Mes en que se generó el saldo (aplica desde el SIGUIENTE)
    saldo_desde_anio = db.Column(db.Integer, nullable=True)

    @property
    def nombre_display(self):
        """Devuelve el nombre de pantalla: nombre_identificador si existe, sino nombre."""
        return self.nombre_identificador or self.nombre

    # La relación inversa se define desde Casa
    def __repr__(self):
        return f"<GrupoCliente {self.nombre}>"
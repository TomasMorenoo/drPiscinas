from app import db

class GrupoCliente(db.Model):
    __tablename__ = 'grupos_clientes'
    
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    
    # La relación inversa se define desde Casa
    def __repr__(self):
        return f"<GrupoCliente {self.nombre}>"
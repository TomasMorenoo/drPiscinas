from app import db

class CierreMes(db.Model):
    __tablename__ = 'cierres_mes'
    
    id = db.Column(db.Integer, primary_key=True)
    mes = db.Column(db.Integer, nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    
    def __repr__(self):
        return f"<CierreMes {self.mes}/{self.anio}>"
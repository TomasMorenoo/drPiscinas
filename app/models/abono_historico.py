from app import db

class AbonoHistorico(db.Model):
    __tablename__ = 'abonos_historicos'
    id = db.Column(db.Integer, primary_key=True)
    casa_id = db.Column(db.Integer, db.ForeignKey('casas.id'), nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    
    # El precio que quedó congelado para ese mes
    monto = db.Column(db.Float, nullable=False)

    casa = db.relationship('Casa', backref=db.backref('historial_abonos', lazy=True))
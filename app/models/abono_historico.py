from app import db
class AbonoHistorico(db.Model):
    __tablename__ = 'abonos_historicos'
    id = db.Column(db.Integer, primary_key=True)
    casa_id = db.Column(db.Integer, db.ForeignKey('casas.id'), nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    
    pagado = db.Column(db.Boolean, default=False)
    # NUEVO ESTADO: Para saber si ya le mandaste el WhatsApp
    mensaje_enviado = db.Column(db.Boolean, default=False)

    casa = db.relationship('Casa', backref=db.backref('historial_abonos', lazy=True))
from app import db

class AbonoHistorico(db.Model):
    __tablename__ = 'abonos_historicos'

    __table_args__ = (
        db.Index('idx_abono_casa_mes_anio', 'casa_id', 'mes', 'anio'),
    )

    id = db.Column(db.Integer, primary_key=True)
    casa_id = db.Column(db.Integer, db.ForeignKey('casas.id'), nullable=False)
    mes = db.Column(db.Integer, nullable=False)
    anio = db.Column(db.Integer, nullable=False)
    monto = db.Column(db.Float, nullable=False)
    
    pagado = db.Column(db.Boolean, default=False)
    mensaje_enviado = db.Column(db.Boolean, default=False)
    
    monto_pagado = db.Column(db.Float, default=0.0)
    
    cobrado_por = db.Column(db.String(100), nullable=True)
    fecha_pago = db.Column(db.DateTime, nullable=True)
    
    transaccion_id = db.Column(db.String(36), nullable=True)
    
    # LA MEMORIA INTERNA: Para que múltiples pagos en el mismo mes no se pisen
    detalle_pagos = db.Column(db.String(500), nullable=True)

    casa = db.relationship('Casa', backref=db.backref('historial_abonos', lazy=True))
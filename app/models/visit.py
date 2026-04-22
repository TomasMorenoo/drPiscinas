from app import db
from datetime import datetime

class Visit(db.Model):
    __tablename__ = "visits"

    __table_args__ = (
        db.Index('idx_visit_casa_id', 'casa_id'),
        db.Index('idx_visit_fecha', 'fecha'),
    )

    id = db.Column(db.Integer, primary_key=True)

    casa_id = db.Column(
        db.Integer,
        db.ForeignKey("casas.id"),
        nullable=False
    )

    promo_id = db.Column(
        db.Integer,
        db.ForeignKey("promos.id"),
        nullable=True
    )

    # --- NUEVO: Guardar quién cargó la visita ---
    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True
    )

    fecha = db.Column(
        db.Date,
        nullable=False,
        default=datetime.utcnow
    )

    observaciones = db.Column(db.String(255))

    # relaciones
    productos = db.relationship("VisitProduct", backref="visit", lazy=True)
    casa = db.relationship("Casa", backref="visitas")
    promo = db.relationship("Promo", backref="visitas")
    usuario = db.relationship("User", backref="visitas_creadas") # NUEVA RELACIÓN

    def __repr__(self):
        return f"<Visit casa={self.casa_id} fecha={self.fecha}>"
    
    def calcular_total(self):
        from app.models.abono_historico import AbonoHistorico
        
        total = 0.0
        mes_cerrado = AbonoHistorico.query.filter_by(mes=self.fecha.month, anio=self.fecha.year).first() is not None

        if self.promo and self.promo.precio:
            total += float(self.promo.precio)

        for vp in self.productos:
            if mes_cerrado and vp.precio_unitario:
                total += float(vp.cantidad) * float(vp.precio_unitario)
            else:
                total += float(vp.cantidad) * float(vp.product.precio)

        return round(total, 2)
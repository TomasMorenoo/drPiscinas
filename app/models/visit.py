from app import db
from datetime import datetime

class Visit(db.Model):
    __tablename__ = "visits"

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
        total = 0.0

        if self.promo and self.promo.precio:
            total += float(self.promo.precio)

        for vp in self.productos:
            if vp.precio_unitario:
                total += float(vp.cantidad) * float(vp.precio_unitario)

        return round(total, 2)
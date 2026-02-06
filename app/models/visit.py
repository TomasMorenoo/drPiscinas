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

    def __repr__(self):
        return f"<Visit casa={self.casa_id} fecha={self.fecha}>"
    
    def calcular_total(self):
        total = 0

        # sumar promo (si existe)
        if self.promo and self.promo.precio:
            total += float(self.promo.precio)

        # sumar productos
        for vp in self.productos:
            if vp.product and vp.product.precio:
                total += float(vp.cantidad) * float(vp.product.precio)

        return round(total, 2)


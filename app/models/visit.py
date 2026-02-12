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
        total = 0.0

        # 1. Sumar promo (si existe)
        # Nota: Si también cambias mucho los precios de las promos, 
        # lo ideal sería aplicar la misma lógica de "precio_capturado" aquí.
        if self.promo and self.promo.precio:
            total += float(self.promo.precio)

        # 2. Sumar productos usando el precio CONGELADO
        for vp in self.productos:
            # Usamos vp.precio_unitario (el que guardamos al crear la visita)
            # y NO vp.product.precio (que es el precio actual del mercado)
            if vp.precio_unitario:
                total += float(vp.cantidad) * float(vp.precio_unitario)

        return round(total, 2)


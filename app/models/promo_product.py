from app import db

class PromoProduct(db.Model):
    __tablename__ = "promo_products"

    id = db.Column(db.Integer, primary_key=True)

    promo_id = db.Column(
        db.Integer,
        db.ForeignKey("promos.id"),
        nullable=False
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id"),
        nullable=False
    )

    cantidad = db.Column(db.Numeric(10, 2), nullable=False)

    # 🔴 ESTO FALTABA
    promo = db.relationship(
        "Promo",
        back_populates="productos"
    )

    product = db.relationship("Product")

    def __repr__(self):
        return f"<PromoProduct promo={self.promo_id} product={self.product_id} cant={self.cantidad}>"

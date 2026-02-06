from app import db

class VisitProduct(db.Model):
    __tablename__ = "visit_products"

    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    cantidad = db.Column(db.Numeric(10,2), nullable=False)

    product = db.relationship("Product")

    def __repr__(self):
        return f"<VisitProduct {self.product.nombre} x {self.cantidad}>"

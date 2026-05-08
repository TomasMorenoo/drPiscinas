from app import db
from datetime import datetime

class MovimientoStock(db.Model):
    __tablename__ = "movimientos_stock"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    tipo = db.Column(db.String(20), nullable=False)  # 'ingreso', 'ajuste'
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    motivo = db.Column(db.String(200))
    usuario = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=True)

    product = db.relationship("Product", backref="movimientos")

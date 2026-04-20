from app import db
from datetime import date

class Pausa(db.Model):
    __tablename__ = "pausas"

    id = db.Column(db.Integer, primary_key=True)
    casa_id = db.Column(db.Integer, db.ForeignKey("casas.id"), nullable=False)
    desde = db.Column(db.Date, nullable=False)
    hasta = db.Column(db.Date, nullable=True)
    pausado_por = db.Column(db.String(100), nullable=True)

    casa = db.relationship("Casa", backref=db.backref("historial_pausas", lazy=True))

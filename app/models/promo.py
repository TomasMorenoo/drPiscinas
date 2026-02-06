from app import db

class Promo(db.Model):
    __tablename__ = "promos"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    productos = db.relationship(
        "PromoProduct",
        back_populates="promo",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<Promo {self.nombre}>"

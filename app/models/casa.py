from app import db
from sqlalchemy import UniqueConstraint

class Casa(db.Model):
    __tablename__ = "casas"

    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "barrio_id",
            "numero",
            name="uq_casa_country_barrio_numero"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(50), nullable=False)
    precio_base = db.Column(db.Numeric(10, 2), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    country_id = db.Column(
        db.Integer,
        db.ForeignKey("countries.id"),
        nullable=False
    )

    barrio_id = db.Column(
        db.Integer,
        db.ForeignKey("barrios.id"),
        nullable=True
    )

    def __repr__(self):
        return f"<Casa {self.numero}>"

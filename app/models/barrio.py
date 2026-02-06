from app import db

class Barrio(db.Model):
    __tablename__ = "barrios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    activo = db.Column(db.Boolean, default=True)

    country_id = db.Column(
        db.Integer,
        db.ForeignKey("countries.id"),
        nullable=False
    )

    casas = db.relationship(
        "Casa",
        backref="barrio",
        lazy=True
    )

    __table_args__ = (
        db.UniqueConstraint(
            "nombre",
            "country_id",
            name="uq_barrio_country"
        ),
    )

    def __repr__(self):
        return "<Barrio {}>".format(self.nombre)

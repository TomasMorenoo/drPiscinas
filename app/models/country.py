from app import db

class Country(db.Model):
    __tablename__ = "countries"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False, unique=True)
    activo = db.Column(db.Boolean, default=True)

    barrios = db.relationship(
        "Barrio",
        backref="country",
        lazy=True
    )

    casas = db.relationship(
        "Casa",
        backref="country",
        lazy=True
    )

    def __repr__(self):
        return f"<Country {self.nombre}>"

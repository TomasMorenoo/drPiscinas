from app import db

class VisitPromo(db.Model):
    __tablename__ = "visit_promos"

    id = db.Column(db.Integer, primary_key=True)

    visit_id = db.Column(
        db.Integer,
        db.ForeignKey("visits.id"),
        nullable=False
    )

    promo_id = db.Column(
        db.Integer,
        db.ForeignKey("promos.id"),
        nullable=False
    )

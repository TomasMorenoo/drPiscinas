from app import db
from datetime import datetime

class VisitMedia(db.Model):
    __tablename__ = "visit_media"

    id = db.Column(db.Integer, primary_key=True)
    visit_id = db.Column(db.Integer, db.ForeignKey("visits.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    tipo = db.Column(db.String(10), nullable=False)  # 'foto' o 'video'
    subido_por = db.Column(db.String(100))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

    visit = db.relationship("Visit", backref="media")

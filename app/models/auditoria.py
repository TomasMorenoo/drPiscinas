from app import db
from datetime import datetime


class AuditoriaLog(db.Model):
    """
    Registro de auditoría para todas las acciones importantes del sistema.
    """
    __tablename__ = "auditoria_logs"

    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.now)
    usuario = db.Column(db.String(100), nullable=False)
    accion = db.Column(db.String(100), nullable=False)
    detalle = db.Column(db.Text, nullable=True)
    ip = db.Column(db.String(45), nullable=True)

    def __repr__(self):
        return f"<AuditoriaLog {self.id} {self.accion} by {self.usuario}>"

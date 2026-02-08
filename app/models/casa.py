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
    precio_anterior = db.Column(db.Float, nullable=True)
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
    
    def obtener_gastos_mensuales(self, mes, anio):
        """Calcula abono + productos extras de un mes específico"""
        total_extras = 0
        # Filtramos las visitas de esta casa por mes y año
        for visita in self.visitas:
            if visita.fecha.month == mes and visita.fecha.year == anio:
                # Sumamos productos extra de esa visita
                for vp in visita.productos:
                    total_extras += float(vp.cantidad) * float(vp.product.precio)
                # Si usó una promo, también la sumamos
                if visita.promo:
                    total_extras += float(visita.promo.precio)
                    
        return {
            "abono": float(self.precio_base),
            "extras": round(total_extras, 2),
            "total": round(float(self.precio_base) + total_extras, 2)
        }

    def nombre_formateado(self):
        """Retorna 'Barrio Número' o 'Country Número' según corresponda"""
        if self.barrio:
            # Si tiene barrio, ignoramos el nombre del country para abreviar
            return f"{self.barrio.nombre} {self.numero}"
        
        # Si no tiene barrio, usamos el nombre del country
        return f"{self.country.nombre} {self.numero}"

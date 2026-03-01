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
    nombre_cliente = db.Column(db.String(100), nullable=True) # Opcional
    telefono = db.Column(db.String(50), nullable=True)
    
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
    
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_clientes.id"), nullable=True)
    grupo = db.relationship("GrupoCliente", backref=db.backref("casas", lazy=True))

    def __repr__(self):
        return f"<Casa {self.numero}>"
    
    def obtener_gastos_mensuales(self, mes, anio):
        """Calcula abono + productos extras de un mes específico"""
        from app.models.abono_historico import AbonoHistorico
        
        total_extras = 0
        mes_cerrado = AbonoHistorico.query.filter_by(mes=mes, anio=anio).first() is not None

        for visita in self.visitas:
            if visita.fecha.month == mes and visita.fecha.year == anio:
                for vp in visita.productos:
                    # Si está cerrado usa el precio histórico, sino el precio vivo actual
                    if mes_cerrado and vp.precio_unitario:
                        total_extras += float(vp.cantidad) * float(vp.precio_unitario)
                    else:
                        total_extras += float(vp.cantidad) * float(vp.product.precio)
                
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
    
    def obtener_saldo_anterior(self, mes, anio):
        """Calcula la deuda o saldo a favor acumulado revisando el historial mes a mes"""
        saldo = 0.0
        for hist in self.historial_abonos:
            # Solo evaluamos los meses ANTERIORES al que estamos consultando en pantalla
            if hist.anio < anio or (hist.anio == anio and hist.mes < mes):
                gastos = self.obtener_gastos_mensuales(hist.mes, hist.anio)
                total_hist = gastos['total']
                pagado_hist = float(getattr(hist, 'monto_pagado', 0) or 0)
                
                # Si tiene el Tilde Verde pero el monto dice 0, asumimos que pagó el 100%
                if getattr(hist, 'pagado', False) and pagado_hist == 0:
                    pagado_hist = total_hist
                    
                # Si el mes salía $10.000 y pagó $15.000, la resta da -$5.000 (a favor).
                saldo += (total_hist - pagado_hist)
                
        return round(saldo, 2)
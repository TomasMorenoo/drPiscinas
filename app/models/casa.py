from app import db
from sqlalchemy import UniqueConstraint
from datetime import datetime

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
    nombre_cliente = db.Column(db.String(100), nullable=True)
    telefono = db.Column(db.String(50), nullable=True) 
    email = db.Column(db.String(120), nullable=True)
    
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    
    country_id = db.Column(db.Integer, db.ForeignKey("countries.id"), nullable=False)
    barrio_id = db.Column(db.Integer, db.ForeignKey("barrios.id"), nullable=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_clientes.id"), nullable=True)
    grupo = db.relationship("GrupoCliente", backref=db.backref("casas", lazy=True))
    
    inactivado_por = db.Column(db.String(100), nullable=True)
    fecha_inactivacion = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return f"<Casa {self.numero}>"
    
    def obtener_gastos_mensuales(self, mes, anio):
        from app.models.abono_historico import AbonoHistorico
        total_extras = 0

        # Buscamos si existe la "foto" histórica de ese mes
        hist = AbonoHistorico.query.filter_by(casa_id=self.id, mes=mes, anio=anio).first()
        mes_cerrado = hist is not None

        for visita in self.visitas:
            if visita.fecha.month == mes and visita.fecha.year == anio:
                # No cobrar visitas anteriores a la fecha de alta del cliente en el sistema
                if self.fecha_creacion:
                    _fv = visita.fecha.date() if isinstance(visita.fecha, datetime) else visita.fecha
                    _fa = self.fecha_creacion.date() if isinstance(self.fecha_creacion, datetime) else self.fecha_creacion
                    if _fv < _fa:
                        continue
                for vp in visita.productos:
                    if mes_cerrado and vp.precio_unitario:
                        total_extras += float(vp.cantidad) * float(vp.precio_unitario)
                    else:
                        total_extras += float(vp.cantidad) * float(vp.product.precio)

                if visita.promo:
                    total_extras += float(visita.promo.precio)

        # MAGIA: Si hay historial, usa el precio congelado. Si no, usa el actual (precio_base).
        abono_final = float(hist.monto) if hist else float(self.precio_base or 0)

        return {
            "abono": abono_final,
            "extras": round(total_extras, 2),
            "total": round(abono_final + total_extras, 2)
        }

    def nombre_formateado(self):
        num_str = "" if self.numero.upper() == "S/N" else f" {self.numero}"
        
        if self.barrio:
            return f"{self.barrio.nombre}{num_str}"
        return f"{self.country.nombre}{num_str}"
    
    def obtener_saldo_anterior(self, mes, anio):
        saldo = 0.0
        historiales_ordenados = sorted(self.historial_abonos, key=lambda x: (x.anio, x.mes))

        for hist in historiales_ordenados:
            if hist.anio < anio or (hist.anio == anio and hist.mes < mes):
                abono_hist = float(hist.monto)
                extras_hist = 0.0
                for visita in self.visitas:
                    if visita.fecha.month == hist.mes and visita.fecha.year == hist.anio:
                        # No cobrar visitas anteriores a la fecha de alta del cliente en el sistema
                        if self.fecha_creacion:
                            _fv = visita.fecha.date() if isinstance(visita.fecha, datetime) else visita.fecha
                            _fa = self.fecha_creacion.date() if isinstance(self.fecha_creacion, datetime) else self.fecha_creacion
                            if _fv < _fa:
                                continue
                        for vp in visita.productos:
                            if vp.precio_unitario:
                                extras_hist += float(vp.cantidad) * float(vp.precio_unitario)
                            else:
                                extras_hist += float(vp.cantidad) * float(vp.product.precio)
                        if visita.promo:
                            extras_hist += float(visita.promo.precio)

                total_hist = abono_hist + extras_hist
                pagado_hist = float(getattr(hist, 'monto_pagado', 0) or 0)

                saldo += total_hist
                saldo -= pagado_hist

                # Reseteamos el saldo a 0 si la cuota figura pagada completamente por otro medio
                if getattr(hist, 'pagado', False) and pagado_hist == 0 and saldo > 0.01:
                    saldo = 0.0

        return round(saldo, 2)


class HistorialAumento(db.Model):
    __tablename__ = "historial_aumentos"
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    descripcion = db.Column(db.String(255), nullable=False)
    casas_afectadas = db.Column(db.Integer, nullable=False)
    mes_desde = db.Column(db.Integer, nullable=True)
    anio_desde = db.Column(db.Integer, nullable=True)
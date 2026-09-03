import unittest
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from app import create_app, db
from app.models.casa import Casa
from app.models.country import Country
from app.models.grupo import GrupoCliente
from app.models.pausa import Pausa
from app.models.abono_historico import AbonoHistorico
from app.routers.casa_router import asegurar_historial_pasado, actualizar_historial_futuro
from app.routers.dashboard_router import toggle_pago_grupo, sync_abonos, unsync_abonos
from app.models.cierre_mes import CierreMes
from app.routers.grupo_router import estado_cuenta_grupo


class SaldosGrupoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        create_app()
        cls.app = Flask(__name__)
        cls.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        db.init_app(cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.grupo = GrupoCliente(nombre='Prueba', saldo_a_favor=0)
        country = Country(nombre='Prueba')
        self.casa = Casa(numero='39', precio_base=77000, country=country,
                         grupo=self.grupo, fecha_creacion=datetime(2026, 6, 1))
        db.session.add_all([self.grupo, country, self.casa])
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def pagar(self):
        with self.app.test_request_context(json={'mes': 7, 'anio': 2026, 'action': 'advance'}):
            with patch('app.routers.dashboard_router.current_user', SimpleNamespace(username='Admin')):
                response = toggle_pago_grupo.__wrapped__.__wrapped__(self.grupo.id)
                self.assertTrue(response.get_json()['success'])

    def test_congelar_historial_pausado_no_inventa_pago(self):
        db.session.add(Pausa(casa=self.casa, desde=date(2026, 3, 1)))
        db.session.commit()
        asegurar_historial_pasado(self.casa, 77000, 8, 2026)
        db.session.commit()
        self.assertEqual(len(self.casa.historial_abonos), 2)
        for h in self.casa.historial_abonos:
            self.assertEqual(h.monto, 0)
            self.assertEqual(h.monto_pagado, 0)
        self.assertEqual(self.casa.obtener_saldo_anterior(8, 2026), 0)

    def test_credito_casa_no_se_duplica_en_grupo(self):
        db.session.add(Pausa(casa=self.casa, desde=date(2026, 3, 1)))
        h = AbonoHistorico(casa=self.casa, mes=7, anio=2026, monto=0,
                           monto_pagado=77000, pagado=False, mensaje_enviado=True)
        db.session.add(h)
        db.session.commit()
        self.pagar()
        self.assertEqual(self.grupo.saldo_a_favor, 0)
        self.assertEqual(h.monto_pagado, 77000)
        self.assertTrue(h.detalle_pagos.endswith(':0.0'))
        self.assertEqual(self.casa.obtener_saldo_anterior(8, 2026), -77000)

    def test_credito_grupo_sobrante_se_conserva(self):
        self.grupo.saldo_a_favor = 100000
        self.grupo.saldo_desde_mes = 6
        self.grupo.saldo_desde_anio = 2026
        h = AbonoHistorico(casa=self.casa, mes=7, anio=2026, monto=77000,
                           monto_pagado=0, pagado=False, mensaje_enviado=True)
        db.session.add(h)
        db.session.commit()
        self.pagar()
        self.assertEqual(self.grupo.saldo_a_favor, 23000)
        self.assertEqual(self.grupo.ultimo_saldo_aplicado, 77000)
        self.assertEqual(h.monto_pagado, 77000)

    def test_credito_del_mismo_mes_no_se_pierde(self):
        self.grupo.saldo_a_favor = 10000
        self.grupo.saldo_desde_mes = 7
        self.grupo.saldo_desde_anio = 2026
        db.session.add(AbonoHistorico(casa=self.casa, mes=7, anio=2026,
                                      monto=77000, pagado=False, mensaje_enviado=True))
        db.session.commit()
        self.pagar()
        self.assertEqual(self.grupo.saldo_a_favor, 10000)
        self.assertEqual(self.grupo.ultimo_saldo_aplicado, 0)

    def test_reabrir_y_cerrar_conserva_precio_anterior_al_aumento(self):
        julio = AbonoHistorico(casa=self.casa, mes=7, anio=2026, monto=77000,
                               monto_pagado=0, pagado=False, mensaje_enviado=False)
        agosto = AbonoHistorico(casa=self.casa, mes=8, anio=2026, monto=77000,
                                monto_pagado=0, pagado=False)
        db.session.add_all([julio, agosto, CierreMes(mes=7, anio=2026)])
        db.session.commit()
        julio_id = julio.id
        self.casa.precio_base = 85000
        actualizar_historial_futuro(self.casa, 85000, 8, 2026, precio_viejo=77000)
        db.session.commit()
        for route in (unsync_abonos, sync_abonos, sync_abonos):
            with self.app.test_request_context(method='POST', data={'mes': 7, 'anio': 2026}), \
                 patch('app.routers.dashboard_router.current_user', SimpleNamespace(username='Admin')), \
                 patch('app.routers.dashboard_router.url_for', return_value='/dashboard'):
                route.__wrapped__.__wrapped__()
            db.session.expire_all()
            self.assertEqual(db.session.get(AbonoHistorico, julio_id).monto, 77000)
            self.assertEqual(agosto.monto, 85000)
        self.assertEqual(AbonoHistorico.query.filter_by(casa_id=self.casa.id, mes=7, anio=2026).count(), 1)

    def test_cerrar_conserva_proporcional_y_pago_parcial_historicos(self):
        h = AbonoHistorico(casa=self.casa, mes=7, anio=2026, monto=97000,
                           proporcional_anterior=20000, monto_pagado=10000, pagado=False)
        db.session.add(h)
        self.casa.precio_base = 85000
        db.session.commit()
        with self.app.test_request_context(method='POST', data={'mes': 7, 'anio': 2026}), \
             patch('app.routers.dashboard_router.current_user', SimpleNamespace(username='Admin')), \
             patch('app.routers.dashboard_router.url_for', return_value='/dashboard'):
            sync_abonos.__wrapped__.__wrapped__()
        self.assertEqual(h.monto, 97000)
        self.assertEqual(h.proporcional_anterior, 20000)
        self.assertEqual(h.monto_pagado, 10000)

    def test_perfil_grupo_acumula_deuda_y_aplica_credito_desde_mes_siguiente(self):
        self.grupo.saldo_a_favor = 5000
        self.grupo.saldo_desde_mes = 7
        self.grupo.saldo_desde_anio = 2026
        db.session.add_all([
            AbonoHistorico(casa=self.casa, mes=7, anio=2026, monto=77000,
                           monto_pagado=20000, pagado=False),
            AbonoHistorico(casa=self.casa, mes=8, anio=2026, monto=85000,
                           monto_pagado=0, pagado=False),
        ])
        db.session.commit()
        filas = estado_cuenta_grupo(self.grupo, [self.casa])
        self.assertEqual([f['mes'] for f in filas], [8, 7])
        self.assertEqual(filas[0]['saldo'], 137000)
        self.assertEqual(filas[1]['saldo'], 57000)
        self.assertEqual(filas[1]['recibido'], 20000)
        self.assertEqual(filas[1]['credito'], 0)
        self.assertEqual(filas[1]['saldo_anterior'], 0)
        self.assertEqual(filas[0]['saldo_anterior'], 52000)
        self.assertEqual(filas[0]['casas'][0]['saldo_anterior'], 57000)

    def test_perfil_grupo_pausado_y_sin_historial(self):
        self.assertEqual(estado_cuenta_grupo(self.grupo, []), [])
        db.session.add(Pausa(casa=self.casa, desde=date(2026, 7, 1)))
        db.session.add(AbonoHistorico(casa=self.casa, mes=7, anio=2026,
                                      monto=77000, monto_pagado=0, pagado=False))
        db.session.commit()
        fila = estado_cuenta_grupo(self.grupo, [self.casa])[0]
        self.assertEqual(fila['abono'], 0)
        self.assertEqual(fila['saldo'], 0)
        self.assertEqual(fila['estado'], 'Pausado')

    def test_perfil_grupo_no_recalcula_abono_de_alta_historico(self):
        self.casa.fecha_creacion = datetime(2026, 6, 3)
        self.casa.precio_base = 121000
        db.session.add(AbonoHistorico(casa=self.casa, mes=6, anio=2026,
                                      monto=0, monto_pagado=0, pagado=True,
                                      cobrado_por='SISTEMA_ALTA'))
        db.session.commit()
        with patch('app.models.configuracion.Configuracion.get', return_value={'mes': 5, 'anio': 2026}):
            fila = estado_cuenta_grupo(self.grupo, [self.casa])[0]
        self.assertEqual(fila['abono'], 0)
        self.assertEqual(fila['recibido'], 0)
        self.assertEqual(fila['saldo'], 0)

    def test_perfil_grupo_no_agrega_proporcional_no_guardado(self):
        self.casa.fecha_creacion = datetime(2026, 1, 1)
        self.casa.fecha_reactivacion = datetime(2026, 5, 31)
        self.casa.proporcional_pendiente = 22500
        db.session.add(AbonoHistorico(casa=self.casa, mes=6, anio=2026,
                                      monto=110000, monto_pagado=110000, pagado=True))
        db.session.commit()
        fila = estado_cuenta_grupo(self.grupo, [self.casa])[0]
        self.assertEqual(fila['abono'], 110000)
        self.assertEqual(fila['saldo'], 0)


if __name__ == '__main__':
    unittest.main()

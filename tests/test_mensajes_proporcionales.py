import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models.plantilla_mensaje import DEFAULT_TEMPLATE_INDIVIDUAL, PlantillaMensaje
from app.routers.dashboard_router import generar_wa_individual


LEGACY_TEMPLATE = """{resumen_total}
Detalle:
Mes de mantenimiento: ${mantenimiento}
Productos Utilizados: ${extras}
{detalle_productos}
Proporcional mes anterior: ${proporcional_anterior}
Productos mes anterior: ${extras_proporcional_anterior}
{detalle_proporcional_anterior}
Saldo adeudado: ${saldo_anterior}
Saldo a favor: -${saldo_favor}
Entregado: -${pagado}"""


class MensajesProporcionalesTest(unittest.TestCase):
    def mensaje(self, template=LEGACY_TEMPLATE, **kwargs):
        valores = dict(abono_mes=0, extras=0, saldo_anterior_visual=0,
                       pagos_en_este_dashboard=0, proporcional=60000,
                       extras_proporcional=10000,
                       detalle_proporcional=['1Litros de Clarificador'])
        valores.update(kwargs)
        with patch('app.routers.dashboard_router.obtener_detalle_productos',
                   return_value=['1Litros de Clarificador']):
            return generar_wa_individual(
                SimpleNamespace(nombre_cliente='CRISTIAN'), 8, 2026,
                pt=SimpleNamespace(get_template_individual=lambda: template), **valores)

    def test_hudson_215_plantilla_sin_variables_proporcionales(self):
        mensaje = self.mensaje()
        self.assertIn('TOTAL A PAGAR: $70.000', mensaje)
        self.assertIn('Mes de mantenimiento: $60.000', mensaje)
        self.assertIn('Productos Utilizados: $10.000', mensaje)
        self.assertEqual(mensaje.count('* 1Litros de Clarificador'), 1)
        self.assertNotIn('mes anterior:', mensaje)

    def test_plantilla_completa_no_duplica_importes_ni_detalles(self):
        mensaje = self.mensaje(DEFAULT_TEMPLATE_INDIVIDUAL)
        self.assertIn('TOTAL A PAGAR: $70.000', mensaje)
        self.assertEqual(mensaje.count('$60.000'), 1)
        self.assertEqual(mensaje.count('$10.000'), 1)
        self.assertEqual(mensaje.count('* 1Litros de Clarificador'), 1)
        self.assertNotIn('Mes de mantenimiento:', mensaje)

    def test_plantilla_parcial_resuelve_cada_variable(self):
        mensaje = self.mensaje(LEGACY_TEMPLATE + '\nProporcional: ${proporcional}')
        self.assertNotIn('Mes de mantenimiento:', mensaje)
        self.assertIn('Proporcional: $60.000', mensaje)
        self.assertIn('Productos Utilizados: $10.000', mensaje)
        self.assertEqual(mensaje.count('* 1Litros de Clarificador'), 1)

    def test_mes_regular_conserva_importes(self):
        mensaje = self.mensaje(abono_mes=80000, extras=10000,
                               proporcional=0, extras_proporcional=0,
                               detalle_proporcional=[])
        self.assertIn('TOTAL A PAGAR: $90.000', mensaje)
        self.assertIn('Mes de mantenimiento: $80.000', mensaje)
        self.assertIn('Productos Utilizados: $10.000', mensaje)
        self.assertEqual(mensaje.count('* 1Litros de Clarificador'), 1)

    def test_diferido_y_pagos_conservan_total(self):
        mensaje = self.mensaje(abono_mes=80000, proporcional=0,
                               extras_proporcional=0, detalle_proporcional=[],
                               proporcional_anterior=20000,
                               extras_proporcional_anterior=5000,
                               detalle_proporcional_anterior=['Producto anterior'],
                               saldo_anterior_visual=-10000,
                               pagos_en_este_dashboard=15000)
        self.assertIn('TOTAL A PAGAR: $80.000', mensaje)
        self.assertIn('Proporcional mes anterior: $20.000', mensaje)
        self.assertIn('Productos mes anterior: $5.000', mensaje)
        self.assertIn('* Producto anterior', mensaje)
        self.assertIn('Saldo a favor: -$10.000', mensaje)
        self.assertIn('Entregado: -$15.000', mensaje)


if __name__ == '__main__':
    unittest.main()

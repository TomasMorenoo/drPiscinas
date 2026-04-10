# 🏊 Dr. Piscinas

Sistema de gestión integral para empresas de mantenimiento de piscinas. Desarrollado con **Python y Flask**, hosteado en VPS propio con **Docker**.

> Proyecto freelance desarrollado a medida. El acceso es privado y la instalación está a cargo del desarrollador.

---

## 💡 Origen del proyecto

El dueño de Dr. Piscinas pasaba horas de su fin de semana con hoja y papel haciendo el cierre del mes: calculando deudas, actualizando precios, anotando visitas. Le propuse construir una solución digital y lo que antes le llevaba un fin de semana entero, ahora le toma unos minutos.

---

## ✨ Funcionalidades

### 👥 Gestión de Clientes y Estructura
- Alta de **countries, barrios y casas** con toda su información.
- **Agrupación de casas** por cliente: si un cliente tiene varias propiedades, podés ver el detalle individual de cada una y un resumen general del grupo.
- Creación de **empleados** con sistema de roles:
  - 🔑 **Administrador** — acceso total, ve precios y puede operar todo el sistema.
  - 👷 **Empleado** — solo puede cargar visitas, sin acceso a precios ni configuraciones.

### 📋 Visitas
- Registro de visitas realizadas a cada casa.
- Detalle de **productos agregados a la pileta** en cada visita para llevar un conteo mensual automatizado.
- Soporte para cargar **promociones** en las visitas además de productos individuales.

### 💰 Panel de Control y Cobros
- Vista centralizada de **cuánto debe pagar cada cliente en el mes**.
- Botón de **envío directo a WhatsApp** con un mensaje personalizado que incluye todos los detalles mensuales del cliente.
- Botón para **marcar como pagado**.
- **Sistema de deudas**: visualizá qué casas tienen deuda pendiente y desde cuándo.

### 📦 Productos y Promociones
- Alta de **productos** con su precio.
- Creación de **promociones** para aprovechar ofertas y aplicarlas directamente en las visitas.

### 📈 Aumentos de Precios
- **Aumento global** para todos los clientes de una vez.
- **Aumento por country** para ajustar por zona.
- **Aumento individual** por casa para casos particulares.

### 📊 Estadísticas
- Ingreso mensual por **abono** vs ingreso por **productos**.
- Gasto de productos **por temporada** (ajustable).

### 🗺️ Hoja de Ruta
- Opción para **imprimir el estado mensual** al corriente, pensada para llevar encima en papel para quienes prefieren no depender del celular durante el día de trabajo.

---

## 🛠️ Stack Tecnológico

![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)

---

## 🚀 Despliegue

La aplicación corre en un **VPS propio con Ubuntu**, containerizada con **Docker**. El acceso es privado y la instalación y mantenimiento están a cargo del desarrollador.

---

## 👨‍💻 Desarrollador

**Tomás Moreno Bauer**
- 🌐 [portfolio.mobatai.com](https://portfolio.mobatai.com)
- 📧 [morenobauer10@gmail.com](mailto:morenobauer10@gmail.com)
- 💬 [+54 11 3188-1483](https://wa.me/5491131881483)

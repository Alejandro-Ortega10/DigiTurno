# DigiTurno Pro 🚀

Sistema profesional de gestión de turnos y colas en tiempo real. Este proyecto utiliza una arquitectura moderna con **FastAPI** en el backend y **SSE (Server-Sent Events)** para actualizaciones instantáneas en las pantallas de TV, permitiendo que múltiples cajas atiendan de forma independiente.

## 🚀 Características Pro
- **Multicaja:** Soporta múltiples cajeros atendiendo simultáneamente con total independencia.
- **Tiempo Real (SSE):** La pantalla de TV se actualiza al instante sin recargar la página mediante un sistema de Pub/Sub.
- **Seguridad por Roles:** Endpoints protegidos mediante API Keys para Cajeros y Administradores.
- **Tickets PDF:** Generación dinámica de comprobantes en PDF (Paperless) optimizados para impresión térmica de 80mm.
- **Diseño Premium:** Interfaz moderna y responsiva basada en la tipografía *Inter* y estándares de diseño actuales.
- **Logging y Robustez:** Manejo exhaustivo de excepciones y registro de eventos para auditoría.

## 🛠️ Stack Tecnológico
- **Backend:** Python 3.12+, FastAPI, Uvicorn.
- **Base de Datos:** SQLite3 (Persistencia local automática).
- **Generación de PDF:** FPDF2.
- **Frontend:** HTML5, CSS3 (Variables, Grid, Flexbox), JavaScript (Vanilla).

## 📦 Instalación y Configuración

Sigue estos pasos para poner el sistema en marcha en tu máquina local o servidor:

1. **Crear y activar entorno virtual:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Instalar dependencias:**
   ```bash
   pip install fastapi uvicorn fpdf2
   ```

3. **Ejecutar el servidor:**
   ```bash
   python3 -m uvicorn main:app --reload
   ```

## 🌐 Enlaces de Acceso (URL del Servidor)
Una vez iniciado el servidor, accede a través de las siguientes URLs en tu navegador:

| Panel | URL | Descripción |
| :--- | :--- | :--- |
| **Cliente** | [http://localhost:8000/cliente.html](http://localhost:8000/cliente.html) | Solicitud de turnos y obtención de ticket PDF. |
| **Cajero** | [http://localhost:8000/cajero.html](http://localhost:8000/cajero.html) | Atención al cliente (Llamar y Finalizar turnos). |
| **Pantalla TV** | [http://localhost:8000/tv.html](http://localhost:8000/tv.html) | Monitor para sala de espera con alertas sonoras. |
| **Administración** | [http://localhost:8000/admin.html](http://localhost:8000/admin.html) | Estadísticas de atención del día actual. |

## 🔐 Seguridad y API Keys
El sistema utiliza una validación básica por encabezados para proteger las operaciones de gestión:
- **Cajero Key:** `cajero123` (Configurada en el panel de atención).
- **Admin Key:** `admin123` (Configurada en el panel de estadísticas).

*Nota: En producción, se recomienda cambiar estas claves en el archivo `main.py` o mediante variables de entorno.*

## 📁 Estructura del Proyecto
```text
DigiTurno/
├── main.py                 # Backend FastAPI (API, DB, SSE, PDF)
├── requirements.txt        # Lista de dependencias
├── turnos.db               # Base de datos SQLite (se crea al iniciar)
└── static/                 # Frontend (Archivos estáticos)
    ├── cliente.html        # Interfaz de solicitud de turno
    ├── cajero.html         # Interfaz de atención (Cajeros)
    ├── tv.html             # Interfaz de visualización pública (TV)
    └── admin.html          # Interfaz de métricas
```

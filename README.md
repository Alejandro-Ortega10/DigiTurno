# Digiturno Paperless 🍃

Sistema integral multiplataforma para la gestión de colas y turnos de atención. Diseñado bajo una arquitectura de micro-API RESTFUL, este proyecto elimina la necesidad de hardware de impresión térmica mediante la generación dinámica de comprobantes PDF (Paperless) accesibles vía escaneo QR.

## 🚀 Características Principales

- **Cero Residuos (Paperless):** Generación de tickets en formato PDF directamente al dispositivo móvil del cliente.
- **Roles Desacoplados:** Interfaces web estáticas e independientes para Cliente, Cajero, Tablero TV y Administrador.
- **Tiempo Real Simulado:** El tablero de TV utiliza *polling* optimizado para evadir la memoria caché de los Smart TVs.
- **Ligero y Rápido:** Backend construido con FastAPI y persistencia en SQLite, ideal para despliegues en servidores Linux (Ubuntu Server) o dispositivos embebidos.

## 🛠️ Stack Tecnológico

- **Backend:** Python 3.11+, FastAPI, Uvicorn
- **Base de Datos:** SQLite3 (Integrada)
- **Generación de PDF:** FPDF2
- **Frontend:** HTML5, CSS3, JavaScript (Vanilla, Fetch API)

## 📁 Estructura del Proyecto

```text
digiturno_completo/
├── main.py                 # Lógica core, endpoints de la API y DB
├── requirements.txt        # Dependencias de Python
├── .gitignore              # Archivos excluidos del control de versiones
├── README.md               # Documentación del proyecto
└── static/                 # Interfaces de usuario (Frontend)
    ├── cliente.html        # Vista móvil para escanear QR y obtener PDF
    ├── cajero.html         # Panel de control para el empleado
    ├── tv.html             # Pantalla de sala de espera
    └── admin.html          # Panel de métricas y estadísticas

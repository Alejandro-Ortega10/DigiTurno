from fastapi import FastAPI, Response, HTTPException, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from fpdf import FPDF
import sqlite3
import datetime
import asyncio
import json
import logging
import os

# --- 1. CONFIGURACIÓN DE LOGGING ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("DigiTurno")

app = FastAPI(title="DigiTurno API")

# --- 2. CONFIGURACIÓN Y SEGURIDAD ---
PREFIJOS = {
    "caja": "C",
    "asesoria": "A",
}

# En un entorno real, estas claves vendrían de variables de entorno (.env)
API_KEYS = {
    "cajero": "cajero123",
    "admin": "admin123"
}

# --- 3. MANAGER DE CONEXIONES (SSE Pub/Sub - Punto 5) ---
class ConnectionManager:
    def __init__(self):
        self.active_queues: list[asyncio.Queue] = []

    async def subscribe(self):
        queue = asyncio.Queue()
        self.active_queues.append(queue)
        logger.info(f"Nueva pantalla de TV conectada. Total: {len(self.active_queues)}")
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self.active_queues:
            self.active_queues.remove(queue)
            logger.info(f"Pantalla de TV desconectada. Restantes: {len(self.active_queues)}")

    async def broadcast(self, message: dict):
        for queue in self.active_queues:
            await queue.put(message)

manager = ConnectionManager()

# --- 4. BASE DE DATOS ---
def init_db():
    try:
        conn = sqlite3.connect('turnos.db')
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS turnos (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       turno_numero TEXT,
                       servicio TEXT,
                       fecha_creacion TIMESTAMP,
                       fecha_atencion TIMESTAMP,
                       estado TEXT DEFAULT 'ESPERA',
                       cajero TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS secuencias (
                       servicio TEXT PRIMARY KEY,
                       ultimo_numero INTEGER DEFAULT 0)''')
        for srv in PREFIJOS:
            c.execute("INSERT OR IGNORE INTO secuencias (servicio, ultimo_numero) VALUES (?, 0)", (srv,))
        conn.commit()
        conn.close()
        logger.info("Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"Error inicializando la base de datos: {e}")

init_db()

def get_db():
    conn = sqlite3.connect('turnos.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# --- 5. MODELOS Y VALIDACIÓN DE ESQUEMAS ---
class LlamadoRequest(BaseModel):
    cajero: str = Field(..., min_length=3, max_length=50)
    servicio: str = Field(..., pattern="^(caja|asesoria)$")

# --- 6. DEPENDENCIAS DE SEGURIDAD ---
def auth_cajero(x_api_key: str = Header(...)):
    if x_api_key != API_KEYS["cajero"]:
        logger.warning("Intento de acceso no autorizado a funciones de Cajero")
        raise HTTPException(status_code=403, detail="No autorizado")

def auth_admin(x_api_key: str = Header(...)):
    if x_api_key != API_KEYS["admin"]:
        logger.warning("Intento de acceso no autorizado a funciones de Admin")
        raise HTTPException(status_code=403, detail="No autorizado")

# --- 7. ENDPOINTS CLIENTE ---
@app.get("/api/cliente/solicitar/{servicio}")
async def solicitar_turno(servicio: str, db: sqlite3.Connection = Depends(get_db)):
    srv = servicio.lower()
    if srv not in PREFIJOS:
        logger.warning(f"Servicio no válido solicitado: {srv}")
        raise HTTPException(status_code=400, detail="Servicio no disponible")

    try:
        prefijo = PREFIJOS[srv]
        row = db.execute(
            "UPDATE secuencias SET ultimo_numero = ultimo_numero + 1 WHERE servicio = ? RETURNING ultimo_numero",
            (srv,)
        ).fetchone()
        
        numero = row["ultimo_numero"]
        turno_numero = f"{prefijo}-{numero:03d}"
        ahora = datetime.datetime.now()

        db.execute(
            "INSERT INTO turnos (turno_numero, servicio, fecha_creacion) VALUES (?, ?, ?)",
            (turno_numero, srv.upper(), ahora)
        )
        db.commit()
        
        logger.info(f"Turno generado exitosamente: {turno_numero} para {srv}")

        # Generación de PDF
        pdf = FPDF(format=(80, 100))
        pdf.add_page()
        pdf.set_font("Helvetica", 'B', 14)
        pdf.cell(0, 8, "SISTEMA DIGITURNO", ln=True, align='C')
        pdf.line(5, 15, 75, 15)
        pdf.set_y(25)
        pdf.set_font("Helvetica", 'B', 36)
        pdf.cell(0, 15, turno_numero, ln=True, align='C')
        pdf.set_font("Helvetica", '', 10)
        pdf.cell(0, 8, f"Servicio: {servicio.upper()}", ln=True, align='C')
        pdf.cell(0, 6, f"{ahora.strftime('%d/%m/%Y %H:%M')}", ln=True, align='C')

        pdf_bytes = bytes(pdf.output())
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=turno_{turno_numero}.pdf"}
        )
    except Exception as e:
        logger.error(f"Error procesando solicitud de turno: {e}")
        raise HTTPException(status_code=500, detail="Error interno al generar el turno")

# --- 8. ENDPOINTS CAJERO ---
@app.post("/api/cajero/llamar", dependencies=[Depends(auth_cajero)])
async def llamar_siguiente(req: LlamadoRequest, db: sqlite3.Connection = Depends(get_db)):
    try:
        ahora = datetime.datetime.now()
        
        # Validación extra: ¿El cajero ya tiene un turno activo sin finalizar?
        activo = db.execute(
            "SELECT id FROM turnos WHERE cajero=? AND estado='LLAMADO'", 
            (req.cajero,)
        ).fetchone()
        if activo:
            raise HTTPException(status_code=400, detail="Debes finalizar el turno actual antes de llamar a otro")

        row = db.execute(
            """UPDATE turnos
               SET estado = 'LLAMADO', cajero = ?, fecha_atencion = ?
               WHERE id = (
                   SELECT id FROM turnos
                   WHERE estado = 'ESPERA' AND servicio = ?
                   ORDER BY id ASC
                   LIMIT 1
               )
               RETURNING id, turno_numero""",
            (req.cajero, ahora, req.servicio.upper())
        ).fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="No hay turnos en espera para este servicio")

        db.commit()
        
        # Notificar a la TV con la LISTA COMPLETA de llamados activos (Punto 5 mejorado)
        activos = db.execute(
            "SELECT turno_numero, cajero FROM turnos WHERE estado='LLAMADO' ORDER BY fecha_atencion DESC"
        ).fetchall()
        
        lista_activos = [dict(a) for a in activos]
        await manager.broadcast(lista_activos)
        
        logger.info(f"Cajero '{req.cajero}' llamó al turno {row['turno_numero']}")
        return {"status": "ok", "turno_llamado": row["turno_numero"], "id": row["id"]}
    
    except HTTPException: raise
    except Exception as e:
        logger.error(f"Error al llamar turno: {e}")
        raise HTTPException(status_code=500, detail="Error en el servidor al procesar el llamado")

@app.post("/api/cajero/finalizar/{turno_id}", dependencies=[Depends(auth_cajero)])
async def finalizar_turno(turno_id: int, db: sqlite3.Connection = Depends(get_db)):
    try:
        db.execute("UPDATE turnos SET estado='ATENDIDO' WHERE id=?", (turno_id,))
        db.commit()
        
        # Actualizar TV (quitar el turno de la lista)
        activos = db.execute(
            "SELECT turno_numero, cajero FROM turnos WHERE estado='LLAMADO' ORDER BY fecha_atencion DESC"
        ).fetchall()
        await manager.broadcast([dict(a) for a in activos])
        
        logger.info(f"Turno ID {turno_id} finalizado")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error al finalizar turno {turno_id}: {e}")
        raise HTTPException(status_code=500, detail="No se pudo finalizar el turno")

# --- 9. ENDPOINTS TV (SSE Optimizado) ---
@app.get("/api/tv/stream")
async def tv_stream():
    async def event_generator():
        queue = await manager.subscribe()
        try:
            # Enviar el estado inicial al conectar (LISTA COMPLETA)
            conn = sqlite3.connect('turnos.db')
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT turno_numero, cajero FROM turnos WHERE estado='LLAMADO' ORDER BY fecha_atencion DESC"
            ).fetchall()
            conn.close()
            
            inicial = [dict(r) for r in rows]
            yield f"data: {json.dumps(inicial)}\n\n"

            while True:
                actual = await queue.get()
                yield f"data: {json.dumps(actual)}\n\n"
        except asyncio.CancelledError:
            manager.unsubscribe(queue)
        except Exception as e:
            logger.error(f"Error en stream SSE: {e}")
            manager.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- 10. ENDPOINTS ADMIN ---
@app.get("/api/admin/estadisticas", dependencies=[Depends(auth_admin)])
async def estadisticas(db: sqlite3.Connection = Depends(get_db)):
    try:
        hoy = datetime.datetime.now().strftime('%Y-%m-%d')
        total_hoy = db.execute(
            "SELECT COUNT(*) FROM turnos WHERE fecha_creacion LIKE ?", (f"{hoy}%",)
        ).fetchone()[0]
        atendidos_hoy = db.execute(
            "SELECT COUNT(*) FROM turnos WHERE estado='ATENDIDO' AND fecha_creacion LIKE ?", (f"{hoy}%",)
        ).fetchone()[0]
        return {"total_creados_hoy": total_hoy, "atendidos_hoy": atendidos_hoy}
    except Exception as e:
        logger.error(f"Error al obtener estadísticas: {e}")
        raise HTTPException(status_code=500, detail="Error al procesar estadísticas")

app.mount("/", StaticFiles(directory="static", html=True), name="static")
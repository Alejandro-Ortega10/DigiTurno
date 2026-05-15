from fastapi import FastAPI, Response, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from fpdf import FPDF
import sqlite3
import datetime
import asyncio
import json
import os

app = FastAPI()

# --- PREFIJOS POR SERVICIO ---
PREFIJOS = {
    "caja": "C",
    "asesoria": "A",
}

# --- BASE DE DATOS ---
def init_db():
    conn = sqlite3.connect('turnos.db')
    c = conn.cursor()
    # Tabla principal de turnos (con columna turno_numero)
    c.execute('''CREATE TABLE IF NOT EXISTS turnos (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   turno_numero TEXT,
                   servicio TEXT,
                   fecha_creacion TIMESTAMP,
                   fecha_atencion TIMESTAMP,
                   estado TEXT DEFAULT 'ESPERA',
                   cajero TEXT)''')
    # Tabla de secuencias por servicio (contador atómico)
    c.execute('''CREATE TABLE IF NOT EXISTS secuencias (
                   servicio TEXT PRIMARY KEY,
                   ultimo_numero INTEGER DEFAULT 0)''')
    # Inicializar contadores para los servicios conocidos
    for srv in PREFIJOS:
        c.execute("INSERT OR IGNORE INTO secuencias (servicio, ultimo_numero) VALUES (?, 0)", (srv,))
    conn.commit()
    conn.close()

init_db()

# --- INYECCIÓN DE DEPENDENCIAS ---
def get_db():
    conn = sqlite3.connect('turnos.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

# --- MODELOS ---
class LlamadoRequest(BaseModel):
    cajero: str
    servicio: str

# --- ENDPOINTS CLIENTE (Crea turno y devuelve PDF) ---
@app.get("/api/cliente/solicitar/{servicio}")
def solicitar_turno(servicio: str, db: sqlite3.Connection = Depends(get_db)):
    srv = servicio.lower()
    prefijo = PREFIJOS.get(srv, srv[0].upper())

    # Incremento atómico del contador de secuencia
    row = db.execute(
        "UPDATE secuencias SET ultimo_numero = ultimo_numero + 1 WHERE servicio = ? RETURNING ultimo_numero",
        (srv,)
    ).fetchone()

    if row is None:
        # Servicio no conocido: insertar fila en secuencias y obtener número
        db.execute("INSERT INTO secuencias (servicio, ultimo_numero) VALUES (?, 1)", (srv,))
        numero = 1
    else:
        numero = row["ultimo_numero"]

    turno_numero = f"{prefijo}-{numero:03d}"
    ahora = datetime.datetime.now()

    db.execute(
        "INSERT INTO turnos (turno_numero, servicio, fecha_creacion) VALUES (?, ?, ?)",
        (turno_numero, srv.upper(), ahora)
    )
    db.commit()

    # Generar Ticket PDF
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

# --- ENDPOINTS CAJERO (Llama y atiende) ---
@app.post("/api/cajero/llamar")
def llamar_siguiente(req: LlamadoRequest, db: sqlite3.Connection = Depends(get_db)):
    ahora = datetime.datetime.now()

    # Auto-finalizar turno activo del cajero antes de llamar otro
    db.execute(
        "UPDATE turnos SET estado = 'ATENDIDO' WHERE cajero = ? AND estado = 'LLAMADO'",
        (req.cajero,)
    )

    # Operación atómica: UPDATE + RETURNING evita race condition
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
    return {"status": "ok", "turno_llamado": row["turno_numero"], "id": row["id"]}

@app.post("/api/cajero/finalizar/{turno_id}")
def finalizar_turno(turno_id: int, db: sqlite3.Connection = Depends(get_db)):
    db.execute("UPDATE turnos SET estado='ATENDIDO' WHERE id=?", (turno_id,))
    db.commit()
    return {"status": "ok"}

# --- ENDPOINTS TV (Monitoreo por SSE) ---
@app.get("/api/tv/estado")
def estado_tv(db: sqlite3.Connection = Depends(get_db)):
    """Endpoint REST de compatibilidad (polling)."""
    row = db.execute(
        "SELECT turno_numero, cajero FROM turnos WHERE estado='LLAMADO' ORDER BY fecha_atencion DESC LIMIT 1"
    ).fetchone()
    if row:
        return {"turno_actual": row["turno_numero"], "cajero": row["cajero"]}
    return {"turno_actual": "-", "cajero": "-"}

@app.get("/api/tv/stream")
async def tv_stream(db: sqlite3.Connection = Depends(get_db)):
    """Endpoint SSE: empuja cambios al cliente sin polling."""
    async def event_generator():
        ultimo = None
        while True:
            row = db.execute(
                "SELECT turno_numero, cajero FROM turnos WHERE estado='LLAMADO' ORDER BY fecha_atencion DESC LIMIT 1"
            ).fetchone()
            actual = dict(row) if row else {"turno_numero": "-", "cajero": "-"}
            if actual != ultimo:
                ultimo = actual
                yield f"data: {json.dumps(actual)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- ENDPOINTS ADMIN (Estadísticas) ---
@app.get("/api/admin/estadisticas")
def estadisticas(db: sqlite3.Connection = Depends(get_db)):
    hoy = datetime.datetime.now().strftime('%Y-%m-%d')
    total_hoy = db.execute(
        "SELECT COUNT(*) FROM turnos WHERE fecha_creacion LIKE ?", (f"{hoy}%",)
    ).fetchone()[0]
    atendidos_hoy = db.execute(
        "SELECT COUNT(*) FROM turnos WHERE estado='ATENDIDO' AND fecha_creacion LIKE ?", (f"{hoy}%",)
    ).fetchone()[0]
    return {"total_creados_hoy": total_hoy, "atendidos_hoy": atendidos_hoy}

app.mount("/", StaticFiles(directory="static", html=True), name="static")
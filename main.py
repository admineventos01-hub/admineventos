from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2 import IntegrityError
import math
import requests
from fastapi.responses import FileResponse
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import os

app = FastAPI(title="SaaS Terrazas - Motor B2B con DB en la Nube")

# Pega tu URI de Supabase aquí adentro (asegúrate de mantener las comillas)
DATABASE_URL = "postgresql://postgres.bxczhsrtqeptyarjlsuv:Adm%40eventos270526@aws-0-us-west-2.pooler.supabase.com:6543/postgres"
N8N_WEBHOOK_URL = "http://localhost:5678/webhook/apartar-evento"

# --- CONFIGURACIÓN DE BASE DE DATOS (POSTGRES QL) ---
def init_db():
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    # En Postgres usamos SERIAL en lugar de AUTOINCREMENT
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventario (
            id SERIAL PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_renta REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reservas (
            id SERIAL PRIMARY KEY,
            fecha_evento TEXT UNIQUE NOT NULL,
            nombre_cliente TEXT NOT NULL,
            total_pagado REAL NOT NULL,
            estado TEXT NOT NULL
        )
    """)

    cursor.execute("SELECT COUNT(*) FROM inventario")
    if cursor.fetchone()[0] == 0:
        servicios = [
            ("Paquete Básico sin DJ", 500.0),
            ("Paquete 1 Audio y DJ", 3000.0),
            ("Paquete 2 Audio y DJ", 5000.0),
            ("Paquete 3 Audio y DJ", 7000.0),
            ("Brincolín 1", 450.0),
            ("Brincolín 2", 650.0),
            ("Brincolín 1 + 2", 900.0),
            ("Decoración 1", 600.0),
            ("Decoración 2", 1200.0),
            ("Mesero", 600.0),
            ("Hora Extra Normal", 350.0),
            ("Hora Extra Tarde", 500.0),
            ("Comida por Persona", 90.0)
        ]
        # En Postgres las variables se inyectan con %s en lugar de ?
        cursor.executemany("INSERT INTO inventario (nombre, precio_renta) VALUES (%s, %s)", servicios)

    conn.commit()
    cursor.close()
    conn.close()

init_db()

# --- MODELOS ---
class CotizacionRequest(BaseModel):
    nombre_cliente: str
    fecha_evento: str
    numero_personas: int
    paquete_audio: str
    brincolin: str
    decoracion: str
    cantidad_meseros: int
    hrs_extra_normal: int
    hrs_extra_tarde: int
    incluir_comida: bool

class ConfirmarReservaRequest(BaseModel):
    fecha_evento: str
    nombre_cliente: str
    total_pagado: float

# --- ENDPOINTS ---

@app.post("/api/cotizar")
def generar_cotizacion(req: CotizacionRequest):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    cursor.execute("SELECT nombre_cliente FROM reservas WHERE fecha_evento = %s AND estado = 'Apartado'", (req.fecha_evento,))
    fecha_ocupada = cursor.fetchone()

    cursor.close()
    conn.close()

    if fecha_ocupada:
        raise HTTPException(
            status_code=400,
            detail=f"La fecha {req.fecha_evento} ya está apartada por: {fecha_ocupada[0]}"
        )

    costo_base_terraza = 3500.0
    personas_base = 50
    costo_personas_extra = 0.0

    if req.numero_personas > personas_base:
        bloques_extra = math.ceil((req.numero_personas - personas_base) / 10)
        costo_personas_extra = bloques_extra * 400.0

    costo_extras = 0.0
    items_desglose = []
    texto_whatsapp = []

    items_desglose.append({"concepto": f"Renta Base de Terraza (hasta {personas_base} pers.)", "monto": costo_base_terraza})
    texto_whatsapp.append(f"Renta Base: ${costo_base_terraza:,.2f}")

    if costo_personas_extra > 0:
        items_desglose.append({"concepto": f"Invitados Extra ({req.numero_personas - personas_base} personas)", "monto": costo_personas_extra})
        texto_whatsapp.append(f"Invitados Extra: ${costo_personas_extra:,.2f}")

    precios_audio = {
        "Paquete Básico sin DJ ($500)": ("Paquete Básico de Audio (sin DJ)", 500.0),
        "Paquete 1 ($3,000)": ("Equipo de Audio y DJ - Paquete 1", 3000.0),
        "Paquete 2 ($5,000)": ("Equipo de Audio y DJ - Paquete 2", 5000.0),
        "Paquete 3 ($7,000)": ("Equipo de Audio y DJ - Paquete 3", 7000.0)
    }
    if req.paquete_audio in precios_audio:
        nombre_clean, monto = precios_audio[req.paquete_audio]
        costo_extras += monto
        items_desglose.append({"concepto": nombre_clean, "monto": monto})
        texto_whatsapp.append(f"{nombre_clean}: ${monto:,.2f}")

    precios_brincolin = {
        "Brincolín 1 ($450)": ("Brincolín Tipo 1", 450.0),
        "Brincolín 2 ($650)": ("Brincolín Tipo 2", 650.0),
        "Brincolín 1 + 2 ($900)": ("Combo Brincolines (1 + 2)", 900.0)
    }
    if req.brincolin in precios_brincolin:
        nombre_clean, monto = precios_brincolin[req.brincolin]
        costo_extras += monto
        items_desglose.append({"concepto": nombre_clean, "monto": monto})
        texto_whatsapp.append(f"{nombre_clean}: ${monto:,.2f}")

    precios_decoracion = {
        "Decoración 1 ($600)": ("Paquete de Decoración 1", 600.0),
        "Decoración 2 ($1,200)": ("Paquete de Decoración 2", 1200.0)
    }
    if req.decoracion in precios_decoracion:
        nombre_clean, monto = precios_decoracion[req.decoracion]
        costo_extras += monto
        items_desglose.append({"concepto": nombre_clean, "monto": monto})
        texto_whatsapp.append(f"{nombre_clean}: ${monto:,.2f}")

    if req.cantidad_meseros > 0:
        monto = req.cantidad_meseros * 600.0
        costo_extras += monto
        items_desglose.append({"concepto": f"Servicio de Meseros ({req.cantidad_meseros})", "monto": monto})
        texto_whatsapp.append(f"Meseros ({req.cantidad_meseros}): ${monto:,.2f}")

    if req.hrs_extra_normal > 0:
        monto = req.hrs_extra_normal * 350.0
        costo_extras += monto
        items_desglose.append({"concepto": f"{req.hrs_extra_normal} Horas Extra (Horario Normal)", "monto": monto})
        texto_whatsapp.append(f"{req.hrs_extra_normal} Hrs Extra Normales: ${monto:,.2f}")

    if req.hrs_extra_tarde > 0:
        monto = req.hrs_extra_tarde * 500.0
        costo_extras += monto
        items_desglose.append({"concepto": f"{req.hrs_extra_tarde} Horas Extra (Horario Nocturno)", "monto": monto})
        texto_whatsapp.append(f"{req.hrs_extra_tarde} Hrs Extra Nocturnas: ${monto:,.2f}")

    if req.incluir_comida:
        monto = req.numero_personas * 90.0
        costo_extras += monto
        items_desglose.append({"concepto": f"Servicio de Comida ({req.numero_personas} pers. a $90 c/u)", "monto": monto})
        texto_whatsapp.append(f"Comida ({req.numero_personas} pers.): ${monto:,.2f}")

    total_evento = costo_base_terraza + costo_personas_extra + costo_extras
    anticipo_requerido = 1000.0 + (costo_extras * 0.5)

    resumen_extras = "\n- ".join(texto_whatsapp)
    mensaje_sugerido = (
        f"Hola {req.nombre_cliente}, para tu evento el {req.fecha_evento} con {req.numero_personas} personas, "
        f"el total es de ${total_evento:,.2f} MXN.\n\n"
        f"Desglose de servicios:\n- {resumen_extras}\n\n"
        f"Apartas con un anticipo de ${anticipo_requerido:,.2f} MXN."
    )

    return {
        "disponible": True,
        "desglose": {
            "terraza_base": costo_base_terraza,
            "personas_extra": costo_personas_extra,
            "total_servicios_extra": costo_extras,
            "total_general": total_evento,
            "anticipo_para_apartar": anticipo_requerido,
            "items_desglose": items_desglose
        },
        "mensaje_whatsapp": mensaje_sugerido
    }

@app.post("/api/apartar")
def apartar_fecha(req: ConfirmarReservaRequest):
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO reservas (fecha_evento, nombre_cliente, total_pagado, estado)
            VALUES (%s, %s, %s, 'Apartado')
        """, (req.fecha_evento, req.nombre_cliente, req.total_pagado))

        conn.commit()

        payload_n8n = {
            "nombre_cliente": req.nombre_cliente,
            "fecha_evento": req.fecha_evento,
            "total_pagado": req.total_pagado,
            "estado": "Apartado"
        }
        try:
            requests.post(N8N_WEBHOOK_URL, json=payload_n8n, timeout=3)
        except requests.exceptions.RequestException:
            print("⚠️ n8n no está escuchando el webhook en este momento.")

    except IntegrityError:
        conn.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Error crítico: La fecha {req.fecha_evento} ya fue bloqueada por alguien más."
        )
    finally:
        cursor.close()
        conn.close()

    return {
        "status": "success",
        "message": f"¡Fecha {req.fecha_evento} guardada con éxito!"
    }

@app.get("/api/cotizar/pdf")
def descargar_pdf(
    nombre_cliente: str,
    fecha_evento: str,
    personas: int,
    total: float,
    anticipo: float,
    conceptos: Optional[List[str]] = Query(None),
    montos: Optional[List[float]] = Query(None)
):
    pdf_filename = f"Cotizacion_{nombre_cliente.replace(' ', '_')}.pdf"

    doc = SimpleDocTemplate(pdf_filename, pagesize=letter, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    story = []
    styles = getSampleStyleSheet()

    style_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], fontSize=22, leading=26, textColor=colors.HexColor("#1A365D"), spaceAfter=10)
    style_texto = ParagraphStyle('Texto', parent=styles['Normal'], fontSize=10, leading=14, textColor=colors.HexColor("#2D3748"))
    style_monto = ParagraphStyle('Monto', parent=style_texto, alignment=2)
    style_bold = ParagraphStyle('Bold', parent=style_texto, fontName="Helvetica-Bold")
    style_bold_monto = ParagraphStyle('BoldMonto', parent=style_monto, fontName="Helvetica-Bold")

    story.append(Paragraph("🎪 COTIZACIÓN DE EVENTO", style_titulo))
    story.append(Paragraph("<b>Logística y Control de Eventos - Terraza OS</b>", style_texto))
    story.append(Spacer(1, 15))

    datos_cliente = [
        [Paragraph("<b>Cliente:</b>", style_texto), Paragraph(nombre_cliente, style_texto),
         Paragraph("<b>Fecha del Evento:</b>", style_texto), Paragraph(fecha_evento, style_texto)],
        [Paragraph("<b>Invitados:</b>", style_texto), Paragraph(f"{personas} personas", style_texto),
         Paragraph("<b>Moneda:</b>", style_texto), Paragraph("MXN (Pesos Mexicanos)", style_texto)]
    ]
    t1 = Table(datos_cliente, colWidths=[90, 170, 110, 150])
    t1.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP'), ('BOTTOMPADDING', (0,0), (-1,-1), 6)]))
    story.append(t1)

    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>DESGLOSE DETALLADO DE SERVICIOS</b>", ParagraphStyle('Sub', parent=styles['Heading2'], fontSize=13, textColor=colors.HexColor("#2B6CB0"))))
    story.append(Spacer(1, 8))

    filas_tabla = [
        [Paragraph("<b>Concepto / Servicio Contratado</b>", style_bold), Paragraph("<b>Importe (MXN)</b>", style_bold_monto)]
    ]

    if conceptos and montos and len(conceptos) == len(montos):
        for c, m in zip(conceptos, montos):
            filas_tabla.append([
                Paragraph(f"• {c}", style_texto),
                Paragraph(f"${m:,.2f}", style_monto)
            ])
    else:
        filas_tabla.append([
            Paragraph("• Renta Base de Terraza e Infraestructura General", style_texto),
            Paragraph(f"${total:,.2f}", style_monto)
        ])

    filas_tabla.append([Paragraph("<b>TOTAL COTIZADO</b>", style_bold), Paragraph(f"<b>${total:,.2f} MXN</b>", style_bold_monto)])
    filas_tabla.append([Paragraph("<b>Garantía de Apartado Requerida (Anticipo)</b>", style_bold), Paragraph(f"<b>${anticipo:,.2f} MXN</b>", style_bold_monto)])
    
    t2 = Table(filas_tabla, colWidths=[370, 150])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor("#F7FAFC")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
        ('PADDING', (0,0), (-1,-1), 7),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,-2), (1,-2), colors.HexColor("#EDF2F7")),
        ('BACKGROUND', (0,-1), (1,-1), colors.HexColor("#EBF8FF")),
    ]))
    story.append(t2)
    
    story.append(Spacer(1, 25))
    story.append(Paragraph("<b>Términos y Condiciones Generales:</b>", style_bold))
    story.append(Paragraph("1. Para asegurar la exclusividad de la fecha es obligatorio liquidar el monto de la garantía de apartado.", style_texto))
    story.append(Paragraph("2. Los servicios extra contratados se operan bajo las normativas técnicas de seguridad de la terraza.", style_texto))
    
    doc.build(story)
    
    return FileResponse(pdf_filename, media_type='application/pdf', filename=pdf_filename)
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="Panel Terraza SaaS", page_icon="🎪", layout="wide")

API_URL = "http://127.0.0.1:8000/api"

st.title("🎪 Panel de Control - Terraza B2B")
st.subheader("Cotizador e Inventario en Tiempo Real")

col1, col2 = st.columns([1, 1])

with col1:
    st.header("🧮 Nueva Cotización")
    nombre = st.text_input("Nombre del Cliente")
    fecha = st.date_input("Fecha del Evento", min_value=datetime.today())
    personas = st.number_input("Número de Personas", min_value=10, value=50, step=10)
    
    st.markdown("---")
    st.subheader("Servicios Extra:")
    
    # 1. Paquetes de Audio
    paquete_audio = st.selectbox(
        "Paquete de Audio y DJ",
        [
            "Sin Audio", 
            "Paquete Básico sin DJ ($500)", 
            "Paquete 1 ($3,000)", 
            "Paquete 2 ($5,000)", 
            "Paquete 3 ($7,000)"
        ]
    )
    
    # 2. Brincolines
    brincolin_opcion = st.selectbox(
        "Brincolín",
        ["Sin Brincolín", "Brincolín 1 ($450)", "Brincolín 2 ($650)", "Brincolín 1 + 2 ($900)"]
    )
    
    # 3. Decoración
    decoracion_opcion = st.selectbox(
        "Decoración",
        ["Sin Decoración", "Decoración 1 ($600)", "Decoración 2 ($1,200)"]
    )
    
    # 4. Meseros
    cantidad_meseros = st.number_input("Cantidad de Meseros ($600 c/u)", min_value=0, value=0, step=1)
    
    # 5. Horas Extra
    c_hrs1, c_hrs2 = st.columns(2)
    with c_hrs1:
        hrs_extra_normal = st.number_input("Horas Extra ($350 c/u)", min_value=0, value=0, step=1)
    with c_hrs2:
        hrs_extra_tarde = st.number_input("Horas Extra Tarde ($500 c/u)", min_value=0, value=0, step=1)
    
    # 6. Comida por Persona
    incluir_comida = st.checkbox(f"Incluir Comida ($90 por persona = ${personas * 90:,.2f} MXN)")

    if st.button("Calcular Cotización"):
        if not nombre:
            st.error("Por favor, introduce el nombre del cliente.")
        else:
            payload = {
                "nombre_cliente": nombre,
                "fecha_evento": str(fecha),
                "numero_personas": int(personas),
                "paquete_audio": paquete_audio,
                "brincolin": brincolin_opcion,
                "decoracion": decoracion_opcion,
                "cantidad_meseros": int(cantidad_meseros),
                "hrs_extra_normal": int(hrs_extra_normal),
                "hrs_extra_tarde": int(hrs_extra_tarde),
                "incluir_comida": incluir_comida
            }
            
            try:
                response = requests.post(f"{API_URL}/cotizar", json=payload)
                if response.status_code == 200:
                    data = response.json()
                    st.session_state['ultima_cotizacion'] = data
                    st.session_state['payload_apartar'] = {
                        "fecha_evento": str(fecha),
                        "nombre_cliente": nombre,
                        "total_pagado": data["desglose"]["anticipo_para_apartar"]
                    }
                else:
                    st.error(f"Error: {response.json()['detail']}")
            except Exception as e:
                st.error("No se pudo conectar con el backend de FastAPI. ¿Está prendido?")

with col2:
    st.header("📋 Resumen y Acciones")
    
    if 'ultima_cotizacion' in st.session_state:
        res = st.session_state['ultima_cotizacion']
        desglose = res["desglose"]
        
        st.metric(label="Total del Evento", value=f"${desglose['total_general']:,.2f} MXN")
        st.metric(label="Anticipo requerido para apartar (50% extras + $1k)", value=f"${desglose['anticipo_para_apartar']:,.2f} MXN")
        
        st.write("### Texto listo para enviar por WhatsApp:")
        st.text_area("Copiar mensaje", value=res["mensaje_whatsapp"], height=160)

        st.write("---")
        st.write("### 🖨️ Documentación Formal")
        
        items = desglose.get("items_desglose", [])
        conceptos_list = [item["concepto"] for item in items]
        montos_list = [item["monto"] for item in items]
        
        params = [
            ("nombre_cliente", nombre),
            ("fecha_evento", str(fecha)),
            ("personas", int(personas)),
            ("total", float(desglose['total_general'])),
            ("anticipo", float(desglose['anticipo_para_apartar']))
        ]
        
        for c in conceptos_list:
            params.append(("conceptos", c))
        for m in montos_list:
            params.append(("montos", m))
        
        try:
            pdf_response = requests.get(f"{API_URL}/cotizar/pdf", params=params)
            if pdf_response.status_code == 200:
                st.download_button(
                    label="📥 Descargar Cotización en PDF",
                    data=pdf_response.content,
                    file_name=f"Cotizacion_{nombre}.pdf",
                    mime="application/pdf"
                )
        except Exception as e:
            st.warning("Asegúrate de tener el backend prendido para generar el PDF.")
        
        st.write("---")
        if st.button("🔒 Confirmar Anticipo y Apartar Fecha"):
            apartar_payload = st.session_state['payload_apartar']
            res_apartar = requests.post(f"{API_URL}/apartar", json=apartar_payload)
            
            if res_apartar.status_code == 200:
                st.success(f"¡Éxito! Fecha bloqueada en la base de datos.")
                del st.session_state['ultima_cotizacion']
            else:
                st.error(f"Error al apartar: {res_apartar.json()['detail']}")
    else:
        st.info("Ingresa los datos de la izquierda y haz clic en 'Calcular Cotización' para ver el desglose aquí.")
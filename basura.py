# --- INTEGRACIÓN AUTOMÁTICA DE NGROK ---
from pyngrok import ngrok

ngrok.set_auth_token("3E1TuhxxMLacNPYey9QbRgz3djE_84NVjynCTCBBmnSG35o4p")

# Abre el túnel público en el puerto 8000 que usa Uvicorn
try:
    tunnels = ngrok.get_tunnels()
    for tunnel in tunnels:
        ngrok.disconnect(tunnel.public_url)

    public_url = ngrok.connect(8000).public_url
    print("\n" + "="*60)
    print(f"🚀 TU API YA ES PÚBLICA EN INTERNET EN ESTA URL: {public_url}")
    print(f"🔗 Interfaz de Swagger para pruebas: {public_url}/docs")
    print("="*60 + "\n")
except Exception as e:
    print(f"⚠️ Nota de Ngrok: No se pudo iniciar automáticamente (tal vez ya hay un túnel activo o falta el Token). Error: {e}")

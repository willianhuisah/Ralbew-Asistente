"""Vigilante de Recordatorios 24/7 de Ralbew (GitHub Actions gratuito).

Se ejecuta en los servidores gratuitos de GitHub, consulta tu base de datos Firestore
y envía las alertas a tu WhatsApp personal mediante la WhatsApp Cloud API de Meta.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

try:
    from zoneinfo import ZoneInfo
    ZONA_HORARIA = ZoneInfo("America/Lima")
except Exception:
    ZONA_HORARIA = timezone(timedelta(hours=-5))
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Configuración de credenciales desde variables de entorno secretas
FIREBASE_KEY_JSON = os.environ.get("FIREBASE_KEY")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID", "1379425321928128")
DESTINATARIO = os.environ.get("DESTINATARIO", "51939271126")

if not FIREBASE_KEY_JSON:
    raise ValueError("Falta la variable de entorno secreta 'FIREBASE_KEY'")

if not WHATSAPP_TOKEN:
    raise ValueError("Falta la variable de entorno secreta 'WHATSAPP_TOKEN'")

# Inicializar Firebase
cred_dict = json.loads(FIREBASE_KEY_JSON)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred)
db = firestore.client()


def enviar_whatsapp(mensaje: str, destinatario: str = DESTINATARIO) -> tuple[bool, str]:
    """Envía un mensaje mediante la WhatsApp Cloud API de Meta."""
    try:
        url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
        clean_to = destinatario.replace("+", "").replace(" ", "").replace("-", "")
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_to,
            "type": "text",
            "text": {"body": mensaje}
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {WHATSAPP_TOKEN}",
            "Content-Type": "application/json"
        }
        req = urllib.request.Request(url, data=data_bytes, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            if resp.status in (200, 201):
                return True, "Mensaje enviado exitosamente"
        return False, "Respuesta inesperada de Meta"
    except Exception as e:
        return False, str(e)


def main():
    ahora = datetime.now(ZONA_HORARIA)
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    hora_actual = ahora.strftime("%H:%M")
    dia_semana_num = ahora.weekday()  # 0=Lunes, ..., 6=Domingo

    print(f"[Vigilante 24/7] Ejecucion: {fecha_hoy} {hora_actual} (Hora Peru)")

    # 1. VERIFICAR RECORDATORIOS DINÁMICOS
    try:
        docs = db.collection("recordatorios_ralbew").where("completado", "==", False).stream()
        for doc in docs:
            data = doc.to_dict()
            doc_fecha = data.get("fecha", fecha_hoy)
            doc_hora = data.get("hora", "")

            # Si el recordatorio es de hoy y su hora programada ya llegó o pasó en esta ventana
            if doc_fecha == fecha_hoy and doc_hora <= hora_actual:
                tarea = data.get("mensaje", "Recordatorio programado")
                tipo = data.get("tipo", "Personal").capitalize()

                texto_alerta = (
                    f"⏰ *Recordatorio de Ralbew (Nube 24/7)*\n\n"
                    f"📌 *{tipo}:* {tarea}\n"
                    f"🕒 *Hora:* {doc_hora} hrs\n"
                    f"📅 *Fecha:* {doc_fecha}\n\n"
                    f"⚡ Enviado puntualmente desde la nube (sin depender de tu laptop encendida)."
                )

                exito, err = enviar_whatsapp(texto_alerta)
                if exito:
                    print(f"✅ Enviado recordatorio: '{tarea}'")
                    doc.reference.update({
                        "completado": True,
                        "notificado_nube": True,
                        "notificado_en": ahora.isoformat()
                    })
                else:
                    print(f"❌ Error al enviar recordatorio: {err}")
    except Exception as e:
        print(f"Error en recordatorios_ralbew: {e}")

    # 2. VERIFICAR AGENDA SEMANAL
    try:
        doc_dia_ref = db.collection("agenda_semanal_ralbew").document(f"dia_{dia_semana_num}")
        doc_dia = doc_dia_ref.get()
        if doc_dia.exists:
            info_dia = doc_dia.to_dict()
            if info_dia.get("activo", True):
                for evento in info_dia.get("eventos", []):
                    ev_hora = evento.get("hora", "")
                    # Si la hora del evento coincide o está dentro de la ventana de los últimos 6 minutos
                    if ev_hora <= hora_actual:
                        # Calcular diferencia de minutos
                        try:
                            h_ev, m_ev = map(int, ev_hora.split(":"))
                            h_act, m_act = map(int, hora_actual.split(":"))
                            dif_min = (h_act * 60 + m_act) - (h_ev * 60 + m_ev)
                        except Exception:
                            dif_min = 0

                        if 0 <= dif_min <= 6:
                            clave_log = f"log_{fecha_hoy}_{dia_semana_num}_{ev_hora}"
                            log_ref = db.collection("historial_envios_nube").document(clave_log)
                            if not log_ref.get().exists:
                                msg_evento = evento.get("mensaje", "Aviso de agenda universitaria/laboral")
                                exito, err = enviar_whatsapp(f"{msg_evento}\n\n☁️ *Ralbew Cloud 24/7*")
                                if exito:
                                    print(f"✅ Enviado evento semanal: '{evento.get('motivo')}'")
                                    log_ref.set({
                                        "fecha": fecha_hoy,
                                        "hora": ev_hora,
                                        "evento": evento.get("motivo", "Agenda"),
                                        "enviado_en": ahora.isoformat()
                                    })
                                else:
                                    print(f"❌ Error enviando evento semanal: {err}")
    except Exception as e:
        print(f"Error en agenda_semanal_ralbew: {e}")

    print("🏁 Vigilante completado.")


if __name__ == "__main__":
    main()

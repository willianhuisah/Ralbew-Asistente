"""Vigilante de Recordatorios 24/7 de Ralbew (GitHub Actions gratuito).

Se ejecuta en los servidores gratuitos de GitHub, consulta tu base de datos Firestore
y envía las alertas (mensuales, agenda semanal y recordatorios dinámicos) a tu
WhatsApp personal mediante la WhatsApp Cloud API de Meta.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo

    ZONA_HORARIA = ZoneInfo("America/Lima")
except Exception:
    ZONA_HORARIA = timezone(timedelta(hours=-5))

import firebase_admin
from firebase_admin import credentials, firestore

# 1. Configuración de credenciales desde variables de entorno secretas
FIREBASE_KEY_JSON = os.environ.get("FIREBASE_KEY")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
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

NOMBRES_DIAS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Rutina mensual fija de pagos y tareas administrativas (días 6, 10, 15, 22, 24 y 28)
RECORDATORIOS_MENSUALES_DEFAULT = {
    6: {
        "dia_mes": 6,
        "hora": "08:00",
        "activo": True,
        "titulo": "Actualizar tipo de cambio INVSER",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 6*\n"
            "Tienes pendiente realizar hoy:\n"
            "• *Actualizar tipo de cambio INVSER*\n"
            "  - Empresa nuestra: INVSER"
        ),
    },
    10: {
        "dia_mes": 10,
        "hora": "08:00",
        "activo": True,
        "titulo": "Pago agua Prescott (Sum: 2522865)",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 10*\n"
            "Tienes pendiente realizar hoy:\n"
            "• *Pago agua Prescott* (Sum: 2522865)\n"
            "  - Servicio: Agua | Pagar a: Sedapal\n"
            "  - Empresa nuestra: T&CH"
        ),
    },
    15: {
        "dia_mes": 15,
        "hora": "08:00",
        "activo": True,
        "titulo": "Peajes PEX + Pago luz Hills Dep 1402 (Sum: 2070126)",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 15*\n"
            "Tienes *2 tareas pendientes* hoy:\n"
            "1. *Peajes PEX:* Menos de S/ 120 recargar S/ 100\n"
            "   - Servicio: Peajes Pex | Pagar a: PEX\n"
            "   - Empresa nuestra: INVSER\n"
            "2. *Pago luz Hills Dep 1402* (Sum: 2070126)\n"
            "   - Servicio: Luz | Pagar a: Luz del Sur\n"
            "   - Empresa nuestra: Jano"
        ),
    },
    22: {
        "dia_mes": 22,
        "hora": "08:00",
        "activo": True,
        "titulo": "Movistar Hills Dep 1402 + Recibo y pago agua Cóndores (Sum: 5059731)",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 22*\n"
            "Tienes *3 tareas pendientes* hoy:\n"
            "1. *Pago internet Hills Dep 1402 Movistar y Celular*\n"
            "   - Servicio: Telefonía | Pagar a: Movistar\n"
            "   - Empresa nuestra: Jano\n"
            "2. *Enviar por correo recibo* (Sum: 5059731 — U: asepsis)\n"
            "   - Servicio: Agua | Proveedor: Sedapal\n"
            "   - Empresa nuestra: Cóndores\n"
            "3. *Pagar agua Cóndores y arreglar* (Sum: 5059731)\n"
            "   - Servicio: Agua | Pagar a: Sedapal\n"
            "   - Empresa nuestra: Cóndores"
        ),
    },
    24: {
        "dia_mes": 24,
        "hora": "08:00",
        "activo": True,
        "titulo": "Pago luz Prescott (Sum: 82715)",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 24*\n"
            "Tienes pendiente realizar hoy:\n"
            "• *Pago luz Prescott* (Sum: 82715)\n"
            "  - Servicio: Luz | Pagar a: Luz del Sur\n"
            "  - Empresa nuestra: T&CH"
        ),
    },
    28: {
        "dia_mes": 28,
        "hora": "08:00",
        "activo": True,
        "titulo": "Actualizar tipo de cambio INVSER",
        "mensaje": (
            "🔔 *Recordatorio Mensual - Día 28*\n"
            "Tienes pendiente realizar hoy:\n"
            "• *Actualizar tipo de cambio INVSER*\n"
            "  - Empresa nuestra: INVSER"
        ),
    },
}


def _sanitizar_parametro_plantilla(texto: str) -> str:
    """Limpia saltos de línea, tabs y espacios múltiples para cumplir reglas de Meta en {{1}}."""
    limpio = texto.replace("\r\n", " | ").replace("\n", " | ").replace("\r", " | ").replace("\t", " ")
    limpio = re.sub(r" {2,}", " ", limpio).strip()
    if len(limpio) > 850:
        limpio = limpio[:847] + "..."
    return limpio


def _post_meta_whatsapp(payload: dict) -> tuple[bool, int, str]:
    """Envía un payload JSON a Meta Graph API y retorna (ok, status_code, detalle)."""
    url = f"https://graph.facebook.com/v19.0/{PHONE_NUMBER_ID}/messages"
    data_bytes = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data_bytes, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status in (200, 201):
                return True, resp.status, body
            return False, resp.status, body
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return False, e.code, err_body
    except Exception as e:
        return False, 0, str(e)


def _hay_ventana_24h_activa(margen_horas: float = 23.5) -> bool:
    """Verifica en Firestore si el usuario interactuó con el bot en las últimas 23.5 horas."""
    try:
        doc = db.collection("estado_sistema_ralbew").document("whatsapp_cloud").get()
        if not doc.exists:
            return False
        data = doc.to_dict() or {}
        epoch = data.get("ultima_interaccion_epoch")
        if not epoch:
            return False
        return (time.time() - float(epoch)) < (margen_horas * 3600.0)
    except Exception:
        return False


def _encolar_pendiente_24h(mensaje: str) -> None:
    """Encola el mensaje completo en Firestore para entregarlo cuando la ventana de 24h abra."""
    try:
        db.collection("estado_sistema_ralbew").document("whatsapp_cloud").set(
            {"cola_pendiente_24h": firestore.ArrayUnion([mensaje])},
            merge=True,
        )
    except Exception as e:
        print(f"⚠️ No se pudo encolar mensaje en cola_pendiente_24h: {e}")


def enviar_whatsapp(mensaje: str, destinatario: str = DESTINATARIO) -> tuple[bool, str]:
    """Envía un mensaje mediante la WhatsApp Cloud API priorizando plantillas 24/7."""
    clean_to = destinatario.replace("+", "").replace(" ", "").replace("-", "")

    # Paso A: Plantillas oficiales 24/7 con parámetro {{1}}
    candidatos_tpl = []
    for t_name in [os.environ.get("WHATSAPP_TEMPLATE_NAME", "").strip(), "recordatorio_ralbew", "aviso_ralbew"]:
        if t_name and t_name not in candidatos_tpl:
            candidatos_tpl.append(t_name)

    candidatos_lang = []
    for lang in [os.environ.get("WHATSAPP_TEMPLATE_LANG", "").strip(), "es_PE", "es"]:
        if lang and lang not in candidatos_lang:
            candidatos_lang.append(lang)

    param_text = _sanitizar_parametro_plantilla(mensaje)
    errores_tpl = []

    for tpl_name in candidatos_tpl:
        for lang in candidatos_lang:
            payload_tpl = {
                "messaging_product": "whatsapp",
                "to": clean_to,
                "type": "template",
                "template": {
                    "name": tpl_name,
                    "language": {"code": lang},
                    "components": [
                        {
                            "type": "body",
                            "parameters": [{"type": "text", "text": param_text}],
                        }
                    ],
                },
            }
            ok, status, detalle = _post_meta_whatsapp(payload_tpl)
            if ok:
                return True, f"Enviado con plantilla {tpl_name} ({lang})"
            errores_tpl.append(f"{tpl_name}/{lang}: HTTP {status} {detalle[:160]}")

    print(f"ℹ️ Ninguna plantilla con {{1}} activa: {' | '.join(errores_tpl)}")

    # Paso B: Fallback cuando no hay plantilla con parámetro aprobada
    payload_txt = {
        "messaging_product": "whatsapp",
        "to": clean_to,
        "type": "text",
        "text": {"body": mensaje},
    }
    ok_txt, status_txt, det_txt = _post_meta_whatsapp(payload_txt)

    if _hay_ventana_24h_activa():
        if ok_txt:
            return True, "Enviado texto libre dentro de ventana 24h"
        return False, f"Error texto libre con ventana 24h activa (HTTP {status_txt}): {det_txt}"

    # Ventana de 24h cerrada o no confirmada: encolar detalle completo y enviar ping hello_world
    _encolar_pendiente_24h(mensaje)
    payload_hw = {
        "messaging_product": "whatsapp",
        "to": clean_to,
        "type": "template",
        "template": {
            "name": "hello_world",
            "language": {"code": "en_US"},
        },
    }
    ok_hw, status_hw, det_hw = _post_meta_whatsapp(payload_hw)
    if ok_hw:
        print(
            "⚠️ Ventana 24h cerrada y sin plantilla en español activa (crea/aprueba 'recordatorio_ralbew' "
            "con variable {{1}} en Meta). Se encoló el detalle completo en cola_pendiente_24h y se envió ping 'hello_world'."
        )
        return True, "Ping hello_world + encolado en cola_pendiente_24h (ventana 24h cerrada)"

    if ok_txt:
        return False, (
            f"Texto aceptado (HTTP {status_txt}) pero ventana 24h cerrada y fallo hello_world "
            f"(HTTP {status_hw}): {det_hw}"
        )
    return False, f"Fallo Meta texto (HTTP {status_txt}: {det_txt}) y hello_world (HTTP {status_hw}: {det_hw})"


def _obtener_mensuales_firestore() -> dict[int, dict]:
    """Lee recordatorios_mensuales_ralbew de Firestore o inicializa con los valores por defecto."""
    col_ref = db.collection("recordatorios_mensuales_ralbew")
    docs = list(col_ref.stream())
    if not docs:
        batch = db.batch()
        for dia, datos in RECORDATORIOS_MENSUALES_DEFAULT.items():
            batch.set(col_ref.document(f"dia_{dia:02d}"), datos)
        batch.commit()
        return dict(RECORDATORIOS_MENSUALES_DEFAULT)

    mensuales = {}
    for d in docs:
        data = d.to_dict() or {}
        dia = data.get("dia_mes")
        if dia is None:
            m = re.search(r"(\d+)", d.id)
            if m:
                dia = int(m.group(1))
        if dia is not None:
            mensuales[int(dia)] = data
    return mensuales


def main():
    ahora = datetime.now(ZONA_HORARIA)
    fecha_hoy = ahora.strftime("%Y-%m-%d")
    hora_actual = ahora.strftime("%H:%M")
    dia_semana_num = ahora.weekday()  # 0=Lunes, ..., 6=Domingo
    dia_mes = ahora.day

    print(f"[Vigilante 24/7] Ejecucion: {fecha_hoy} {hora_actual} (Hora Peru)")

    # 0. VERIFICAR RECORDATORIOS MENSUALES FIJOS (Días 6, 10, 15, 22, 24 y 28)
    try:
        mensuales = _obtener_mensuales_firestore()
        info_mes = mensuales.get(dia_mes)
        if info_mes and info_mes.get("activo", True):
            hora_prog = str(info_mes.get("hora", "08:00")).strip() or "08:00"
            if hora_actual >= hora_prog:
                clave_mensual = f"mensual_{fecha_hoy}"
                hist_ref = db.collection("historial_envios_nube").document(clave_mensual)
                if not hist_ref.get().exists:
                    mensaje_mensual = info_mes.get("mensaje") or RECORDATORIOS_MENSUALES_DEFAULT.get(dia_mes, {}).get("mensaje", "")
                    if mensaje_mensual:
                        exito, detalle_envio = enviar_whatsapp(mensaje_mensual)
                        if exito:
                            print(f"✅ Enviado recordatorio mensual día {dia_mes} ({detalle_envio})")
                            hist_ref.set({
                                "fecha": fecha_hoy,
                                "dia_mes": dia_mes,
                                "hora_programada": hora_prog,
                                "enviado_en": ahora.isoformat(),
                                "metodo": detalle_envio,
                                "tipo": "recordatorio_mensual",
                            })
                        else:
                            print(f"❌ Error al enviar recordatorio mensual día {dia_mes}: {detalle_envio}")
                else:
                    print(f"ℹ️ Recordatorio mensual {fecha_hoy} ya fue notificado anteriormente.")
    except Exception as e:
        print(f"Error en recordatorios_mensuales_ralbew: {e}")

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

                exito, detalle_envio = enviar_whatsapp(texto_alerta)
                if exito:
                    print(f"✅ Enviado recordatorio: '{tarea}' ({detalle_envio})")
                    doc.reference.update({
                        "completado": True,
                        "notificado_nube": True,
                        "notificado_en": ahora.isoformat(),
                        "metodo_envio": detalle_envio,
                    })
                else:
                    print(f"❌ Error al enviar recordatorio: {detalle_envio}")
    except Exception as e:
        print(f"Error en recordatorios_ralbew: {e}")

    # 2. VERIFICAR AGENDA SEMANAL
    try:
        nombre_dia = NOMBRES_DIAS[dia_semana_num]
        doc_dia = db.collection("agenda_semanal_ralbew").document(nombre_dia).get()
        if not doc_dia.exists:
            doc_dia = db.collection("agenda_semanal_ralbew").document(f"dia_{dia_semana_num}").get()

        if doc_dia.exists:
            info_dia = doc_dia.to_dict() or {}
            if info_dia.get("activo", True):
                for evento in info_dia.get("eventos", []):
                    ev_hora = evento.get("hora", "")
                    if ev_hora and ev_hora <= hora_actual:
                        try:
                            h_ev, m_ev = map(int, ev_hora.split(":"))
                            h_act, m_act = map(int, hora_actual.split(":"))
                            dif_min = (h_act * 60 + m_act) - (h_ev * 60 + m_ev)
                        except Exception:
                            dif_min = 0

                        if 0 <= dif_min <= 180:
                            clave_log = f"log_{fecha_hoy}_{dia_semana_num}_{ev_hora}"
                            log_ref = db.collection("historial_envios_nube").document(clave_log)
                            if not log_ref.get().exists:
                                msg_evento = evento.get("mensaje", "Aviso de agenda universitaria/laboral")
                                exito, detalle_envio = enviar_whatsapp(f"{msg_evento}\n\n☁️ *Ralbew Cloud 24/7*")
                                if exito:
                                    print(f"✅ Enviado evento semanal: '{evento.get('motivo')}' ({detalle_envio})")
                                    log_ref.set({
                                        "fecha": fecha_hoy,
                                        "hora": ev_hora,
                                        "evento": evento.get("motivo", "Agenda"),
                                        "enviado_en": ahora.isoformat(),
                                        "metodo": detalle_envio,
                                    })
                                else:
                                    print(f"❌ Error enviando evento semanal: {detalle_envio}")
    except Exception as e:
        print(f"Error en agenda_semanal_ralbew: {e}")

    print("🏁 Vigilante completado.")


if __name__ == "__main__":
    main()

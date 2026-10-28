"""
monitor_estado.py — reporta el estado de este bot a Supabase cada 5 minutos.

Uso (agregar en Minas-op.py / anu-ventas.py, cerca de los otros hilos de
fondo como _watchdog):

    from monitor_estado import iniciar_monitor_estado, reportar_evento
    iniciar_monitor_estado()
    ...
    # dentro de reiniciar_juego(), al detectar la desconexión:
    reportar_evento("desconexion", "recnec: sin respuesta tras 3 min")

Todo lo de acá adentro es best-effort: si Supabase no responde o no hay
internet, el bot real sigue jugando sin enterarse — nunca debe poder
trabar el loop principal.

Configuración vía .env (mismo directorio que el bot, o variables de entorno
del sistema):
    SUPABASE_URL         → Project Settings → API → Project URL
    SUPABASE_SERVICE_KEY → Project Settings → API → service_role key
                            (NUNCA la clave "anon" acá, y NUNCA subir esta
                            clave a git ni pegarla en el dashboard público)
    BOT_NOMBRE           → opcional. Si no se define, usa el nombre de la PC
                            en Windows (hostname) automáticamente — cada
                            máquina se identifica sola, sin tener que ir
                            asignando mina-02, mina-03... a mano. Poné algo
                            acá solo si querés un nombre más lindo/corto que
                            el hostname, o si dos PCs comparten hostname.
    BOT_TIPO             → 'mineria' o 'anutrof'
    HEARTBEAT_INTERVALO_SEG → opcional, default 60 (1 min). Poner 30 para
                            pruebas y ver el dashboard actualizarse todavía
                            más rápido.

Detección de caída — dos mecanismos distintos:
  - Cierre manual (Ctrl+C, cierre normal del proceso): se detecta CASI AL
    INSTANTE. Al salir, este módulo manda un aviso explícito a Supabase
    (ver _marcar_detenido) que el dashboard va a mostrar como "caído" en la
    próxima vuelta de refresco (hasta 30s).
  - Caída real (se cuelga, se corta la luz, lo mata Task Manager/kill -9):
    NO hay forma de que el proceso avise nada — no llega a ejecutar código
    al morir así. Se detecta solo por silencio: si no llega un heartbeat
    nuevo en el umbral configurado en el dashboard (OFFLINE_TRAS_SEG), pasa
    a "caído". Bajar HEARTBEAT_INTERVALO_SEG acelera esto, pero ojo: con 10
    bots activos, intervalos muy cortos se acercan rápido al límite de ancho
    de banda gratis de Supabase (2GB/mes).
"""
import os
import time
import socket
import threading
import atexit
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # si no está instalado python-dotenv, se usan solo variables de entorno del sistema

try:
    import requests
except ImportError:
    requests = None  # sin la librería, el módulo se autodeshabilita en vez de romper el import del bot

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
# Si no se define BOT_NOMBRE en el .env, usa el nombre de esta PC en Windows.
# Así cada máquina se identifica sola en el dashboard sin tener que ir
# asignando mina-02, mina-03... a mano y acordarse cuál ya se usó. Si dos
# PCs distintas tuvieran el mismo hostname (raro, pero pasa con clones de
# VM) se pisarían entre sí — en ese caso sí conviene fijar BOT_NOMBRE a mano.
BOT_NOMBRE = os.environ.get("BOT_NOMBRE") or socket.gethostname()
BOT_TIPO = os.environ.get("BOT_TIPO", "mineria")

# Override en .env con HEARTBEAT_INTERVALO_SEG para ajustar. Default 60s:
# balance entre detectar caídas rápido y no acercarse al límite de ancho de
# banda gratis de Supabase con 10 bots reportando en simultáneo.
INTERVALO_HEARTBEAT_SEG = int(os.environ.get("HEARTBEAT_INTERVALO_SEG", "60"))

_BOT_ID_PATH = Path(__file__).resolve().parent / "bot_id.txt"

_habilitado = bool(requests and SUPABASE_URL and SUPABASE_SERVICE_KEY and BOT_NOMBRE)
_actividad_actual = "iniciando"

# Hace cuánto el BOT (no solo este hilo) hizo progreso real de verdad — se
# actualiza desde registrar_progreso() del bot, la misma marca que ya usa su
# watchdog interno para decidir "5 min sin avance -> reiniciar". Un proceso
# puede seguir vivo (y mandando heartbeat) aunque el loop principal esté
# trabado por algo que recnec() no detectó; esto lo distingue en el dashboard
# de un bot que de verdad está jugando.
_ultimo_progreso_bot = time.time()


def _headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _bot_id():
    """uuid persistente por PC — se genera una sola vez y se reusa siempre."""
    if _BOT_ID_PATH.exists():
        return _BOT_ID_PATH.read_text(encoding="utf-8").strip()
    import uuid
    nuevo = str(uuid.uuid4())
    _BOT_ID_PATH.write_text(nuevo, encoding="utf-8")
    return nuevo


def establecer_actividad(texto):
    """Llamar desde el bot para que el próximo heartbeat reporte qué está
    haciendo ahora mismo (ej. establecer_actividad('vendiendo en mercado'))."""
    global _actividad_actual
    _actividad_actual = texto


def marcar_progreso():
    """Enganchado desde registrar_progreso() del bot — cada vez que el bot
    hace algo real (minar, hablar con un NPC, detectar un mapa...) esto se
    actualiza. Es lo que permite distinguir 'el proceso sigue vivo' de
    'el personaje también está jugando'."""
    global _ultimo_progreso_bot
    _ultimo_progreso_bot = time.time()


def reportar_evento(tipo_evento, detalle=""):
    """Manda un evento inmediato (no espera al próximo heartbeat de 5 min).
    Pensado para llamarse desde reiniciar_juego() y similares."""
    if not _habilitado:
        return
    try:
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/bot_eventos",
            headers=_headers(),
            json={"bot_id": _bot_id(), "tipo_evento": tipo_evento, "detalle": detalle},
            timeout=10,
        )
        if r.status_code >= 300:
            print(f"[monitor_estado] ⚠️ evento '{tipo_evento}' rechazado ({r.status_code}): {r.text[:200]}")
    except Exception as e:
        print(f"[monitor_estado] ⚠️ evento '{tipo_evento}' falló: {type(e).__name__}: {e}")
        # best-effort — nunca debe frenar al bot real


# Protege contra la carrera: si un heartbeat normal (timestamp real) y el
# aviso de cierre (timestamp viejo) se mandan casi al mismo tiempo, pueden
# llegar a Supabase en cualquier orden y el heartbeat "real" terminar
# pisando el aviso de cierre. Con este lock, _marcar_detenido() espera a que
# termine cualquier heartbeat en curso antes de mandar el suyo — así el
# aviso de cierre siempre es la última escritura, garantizado.
_lock_heartbeat = threading.Lock()
_detener_loop = threading.Event()


def _enviar_heartbeat():
    payload = {
        "bot_id": _bot_id(),
        "nombre": BOT_NOMBRE,
        "tipo": BOT_TIPO,
        "hostname": socket.gethostname(),
        "ultimo_heartbeat": "now()",
        "actividad": _actividad_actual,
        "segundos_sin_progreso": round(time.time() - _ultimo_progreso_bot),
    }
    with _lock_heartbeat:
        try:
            r = requests.post(
                f"{SUPABASE_URL}/rest/v1/bots",
                headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                # on_conflict por "bot_id" (no "nombre"): bot_id.txt es el
                # identificador estable y único por PC (se genera una sola vez
                # y nunca se comparte entre máquinas). Si dos PCs quedan con el
                # mismo BOT_NOMBRE (por ej. porque el .env se copió tal cual a
                # otra PC sin cambiar el nombre), upsert por "nombre" intenta
                # PISAR el bot_id de la fila ya existente — y esa fila tiene
                # bot_eventos apuntándole, así que Postgres lo rechaza con un
                # 23503 (foreign key violation) en cada heartbeat, para
                # siempre. Con "bot_id" como clave de conflicto, cada PC
                # actualiza únicamente su propia fila sin importar qué nombre
                # tenga configurado.
                params={"on_conflict": "bot_id"},
                json=payload,
                timeout=10,
            )
            if r.status_code >= 300:
                print(f"[monitor_estado] ⚠️ heartbeat rechazado ({r.status_code}): {r.text[:200]}")
                if r.status_code == 409 and "nombre" in r.text:
                    print(f"[monitor_estado] 👉 probablemente otra PC ya está usando BOT_NOMBRE='{BOT_NOMBRE}' — "
                          f"asigná un nombre único a esta PC en el .env")
        except Exception as e:
            print(f"[monitor_estado] ⚠️ heartbeat falló: {type(e).__name__}: {e}")


def _loop_heartbeat():
    primera_vuelta = True
    while not _detener_loop.is_set():
        # Si algo no previsto lanza una excepción acá (fuera de los try/except
        # de _enviar_heartbeat), un hilo de Python simplemente muere en
        # silencio — no hay reintento automático, y el traceback va a stderr,
        # no al log del bot. Esto evita que UN error de cualquier tipo apague
        # el reporte de estado para el resto de la sesión.
        try:
            _enviar_heartbeat()
        except Exception as e:
            print(f"[monitor_estado] ⚠️ error inesperado en el hilo de heartbeat: {type(e).__name__}: {e}")
        if primera_vuelta:
            # El evento "inicio" va DESPUÉS del primer heartbeat: bot_eventos.bot_id
            # es foreign key a bots.bot_id, y en una PC que arranca por primera vez
            # esa fila en bots todavía no existe — mandar el evento antes de
            # crearla siempre fallaba con violación de foreign key (23503).
            reportar_evento("inicio", f"bot arrancado en {socket.gethostname()}")
            primera_vuelta = False
        _detener_loop.wait(INTERVALO_HEARTBEAT_SEG)  # como sleep(), pero corta si _marcar_detenido() ya arrancó


def _marcar_detenido():
    """Se ejecuta al cerrar el proceso de forma normal (Ctrl+C, sys.exit(),
    fin del script). Fuerza el estado a 'caído' de inmediato en vez de
    esperar a que venza el umbral de silencio del dashboard — mandamos
    ultimo_heartbeat muy en el pasado (época unix) para que CUALQUIER umbral
    que use el dashboard lo trate como caído en la próxima vuelta (30s).

    NO se ejecuta en un cierre forzado (Task Manager, kill -9, corte de luz,
    ventana de consola cerrada de golpe) — Windows no le da tiempo al
    proceso de correr código en esos casos. Para esos, la única detección
    posible es por silencio de heartbeat (ver HEARTBEAT_INTERVALO_SEG)."""
    if not _habilitado:
        return
    _detener_loop.set()  # que el hilo no arranque un heartbeat nuevo
    try:
        with _lock_heartbeat:  # esperar a que termine cualquier heartbeat ya en curso
            requests.post(
                f"{SUPABASE_URL}/rest/v1/bots",
                headers={**_headers(), "Prefer": "resolution=merge-duplicates"},
                params={"on_conflict": "bot_id"},
                json={
                    "bot_id": _bot_id(),
                    "nombre": BOT_NOMBRE,
                    "tipo": BOT_TIPO,
                    "ultimo_heartbeat": "1970-01-01T00:00:00Z",
                    "actividad": "detenido manualmente",
                },
                timeout=5,
            )
        requests.post(
            f"{SUPABASE_URL}/rest/v1/bot_eventos",
            headers=_headers(),
            json={"bot_id": _bot_id(), "tipo_evento": "detenido_manual",
                  "detalle": f"proceso cerrado en {socket.gethostname()}"},
            timeout=5,
        )
    except Exception:
        pass


def iniciar_monitor_estado():
    """Arranca el hilo de reporte en segundo plano. Si falta configuración
    en el .env, queda deshabilitado silenciosamente (con un aviso una sola
    vez) en vez de romper el arranque del bot."""
    if not _habilitado:
        if requests is None:
            print("[monitor_estado] deshabilitado — falta instalar: pip install requests python-dotenv")
            return
        faltan = [n for n, v in [("SUPABASE_URL", SUPABASE_URL),
                                  ("SUPABASE_SERVICE_KEY", SUPABASE_SERVICE_KEY)] if not v]
        print(f"[monitor_estado] deshabilitado — faltan variables en .env: {', '.join(faltan)}")
        return
    threading.Thread(target=_loop_heartbeat, daemon=True).start()
    atexit.register(_marcar_detenido)
    print(f"[monitor_estado] activo — reportando como '{BOT_NOMBRE}' cada {INTERVALO_HEARTBEAT_SEG}s")

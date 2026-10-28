# Bot Mina — Guía de instalación y uso

## Requisitos del sistema

- Windows 10 / 11
- Python 3.11 (recomendado, misma versión en todos los PCs)
- Dofus Retro v1.47 corriendo en **resolución 1280x1024**
- El juego debe estar en la **pantalla principal** (no en segunda pantalla)

---

## Instalación de dependencias

### 1. Instalar Python 3.11

Descargar desde: https://www.python.org/downloads/release/python-3110/

> Marcar la opción **"Add Python to PATH"** durante la instalación.

### 2. Instalar librerías

Abrir una terminal (cmd) y ejecutar:

```bash
pip install -r requirements.txt
```

### 3. Instalar pywin32 manualmente (obligatorio, requirements.txt no es suficiente)

`pywin32` requiere un paso extra después de instalarse. Sin este paso el bot falla con `ModuleNotFoundError: No module named 'win32gui'` aunque aparezca en `pip list`.

**Paso 1 — Instalar el paquete** (probar en orden hasta que uno funcione):

```bash
pip install pywin32
```
```bash
pip -m install pywin32
```
```bash
py -m pip install pywin32
```
```bash
python -m pip install pywin32
```

**Paso 2 — Ejecutar el post-install** (obligatorio, registra las DLLs en el sistema):

```bash
python "C:\Users\TU_USUARIO\AppData\Local\Programs\Python\Python311\Scripts\pywin32_postinstall.py" -install
```

> Reemplaza `TU_USUARIO` con tu nombre de usuario de Windows.  
> Si usas Python 3.12, cambia `Python311` por `Python312`. Para encontrar la ruta exacta:
> ```bash
> python -c "import sys; print(sys.prefix)"
> ```
> El resultado es la carpeta raíz de Python — agrega `\Scripts\pywin32_postinstall.py` al final.

**Paso 3 — Verificar que quedó instalado:**

```bash
python -c "import win32gui; print('OK')"
```

Si imprime `OK`, está listo. Si sigue fallando, ver sección **Problemas comunes** al final.

---

## Archivos de imágenes requeridos

El bot usa detección por imagen. Todos estos archivos `.png` deben estar en la misma carpeta que el bot:

| Archivo | Para qué sirve |
|---|---|
| `recolectar.png` | Detecta el botón de recolectar mineral |
| `recolectar-2.png` | Detecta mineral no disponible por nivel |
| `jugar-boton.png` | Detecta el botón JUGAR del launcher |
| `laucher.png` | Detecta la ventana del launcher |
| `laucher_barra.png` | Detecta la barra del launcher |
| `nivel-minero.png` | Detecta el ícono del minero enemigo en sala |
| `dadi1.png` … `dadi10.png` | Íconos del aliado en combate |
| `jala1.png` … `jala10.png` | Íconos del enemigo en combate |
| `posimabonta.png` | Ícono de la poción de Bonta |
| `posimarecuerdo.png` | Ícono de la poción de recuerdo |
| `pan.png` | Ícono del pan en inventario |
| `mapa.png` | Referencia de mapa |
| `cerrar_ventanas.png` | Botón para cerrar ventanas del juego |

> Si falta `recolectar-2.png` el bot muestra un warning en el log pero sigue funcionando.

---

## Configuración de pantalla

**Resolución obligatoria: 1280 x 1024**

Todas las coordenadas de clic y detección de píxeles están calibradas para esta resolución. En otra resolución el bot no funcionará correctamente.

Para verificar:
- Click derecho en escritorio → Configuración de pantalla → Resolución: **1280 × 1024**

---

## Cómo ejecutar el bot

### Opción 1 — Desde VS Code
Abrir `Minas-op.py` y presionar el botón ▶ Play.

### Opción 2 — Desde terminal

```bash
cd "C:\Users\TU_USUARIO\Desktop\bots\botmina"
python "Minas-op.py"
```

---

## Cómo testear funciones individuales

Usar el archivo `test_funciones.py`. Descomentar la función que se quiere probar:

```bash
python test_funciones.py
```

---

## Cómo ver posición y color del mouse

```bash
python mouse_info.py
```

Muestra en tiempo real la posición XY y el RGB del pixel bajo el cursor. Al presionar Ctrl+C imprime la línea lista para copiar al código.

---

## Logs

El bot guarda todos los prints en `bot_log.txt` en la misma carpeta, con timestamp por línea.

---

## Comportamientos automáticos del bot

| Comportamiento | Descripción |
|---|---|
| **Watchdog** | Si pasan 5 minutos sin actividad real, cierra y reinicia el juego |
| **Reconexión** | Detecta pantalla de desconexión y vuelve a conectar automáticamente. Si falla en 30s, reinicia el juego |
| **Inventario lleno** | Detecta inventario lleno y va al banco automáticamente |
| **Pelea** | Detecta combate y juega automáticamente usando imágenes de aliados/enemigos |
| **Minero enemigo** | Detecta y enfrenta mineros que bloquean el camino |
| **Reorientación** | Si el bot queda pegado en una sala por más de 30 intentos, cierra ventanas y recalcula el camino |

---

## Problemas comunes

**`ModuleNotFoundError: No module named 'win32gui'`**

Probar en orden hasta que uno funcione:

```bash
pip install pywin32
pip -m install pywin32
py -m pip install pywin32
python -m pip install pywin32
```

Luego ejecutar el post-install obligatorio:

```bash
python "C:\Users\TU_USUARIO\AppData\Local\Programs\Python\Python311\Scripts\pywin32_postinstall.py" -install
```

Si no sabes la ruta exacta:
```bash
python -c "import sys; print(sys.prefix + r'\Scripts\pywin32_postinstall.py')"
```
Copia la ruta que imprime y úsala en el comando anterior.

Verificar:
```bash
python -c "import win32gui; print('OK')"
```

**`cv2.error` al iniciar**
→ Verificar que `recolectar.png` existe en la carpeta del bot

**Bot hace clics en lugares incorrectos**
→ Verificar que la resolución del juego es exactamente 1280×1024 y está en la pantalla principal

**Watchdog reinicia el juego cuando el bot está activo**
→ Verificar que el bot tiene la versión más reciente (las funciones `sala`, `ir_banco`, `inventario`, `minar` y `recnec` ya registran actividad)

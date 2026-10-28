# Arquitectura de `Minas-op.py`

Mapa de funciones del bot de minería para Dofus Retro. El bot controla el
juego a ciegas: no lee memoria ni usa una API, todo se hace leyendo píxeles
de la pantalla (`heart.pixelMatchesColor`), comparando templates de imagen
con OpenCV (`cv2.matchTemplate`) y leyendo texto con OCR (`pytesseract`).
Por eso casi todas las funciones tienen coordenadas y colores "mágicos"
hardcodeados — están calibrados a una resolución de pantalla fija
(1280×1024) y a la posición de las ventanas del juego.

Este documento no reemplaza el código: es un índice para encontrar rápido
qué función hace qué, sin tener que leer 9900 líneas. Los números de línea
son de referencia y se van a desactualizar con el tiempo — si no coinciden,
buscá el nombre de la función con `grep -n "^def nombre" Minas-op.py`.

---

## 1. Flujo general del bot

```
if __name__ == "__main__":        (línea 5432, ~4500 líneas de loop principal)
  while True:
    pelear2() / inventario() / vent_pelea() / recnec() / any_desk()
    sala()                         → maneja la sala especial de pelea/minero
    para cada sala de cada mina:
      minar_ws(posiciones, ...)    → mina las vetas de esa sala
        └─ minar()                 → clickea cada veta y espera a que se agote
        └─ si "atascado" varias pasadas seguidas → caminarMina() (reorienta)

    inventario()                   → ¿inventario lleno?
      └─ si está lleno:
           ir_banco()               → viaja al banco, deposita el mineral minado,
                                        alimenta la mascota (dragopavo)
             └─ ir_mercado()        → viaja al mercado y VENDE todo
                  ├─ vender_mineral()       → por cada mineral: lee precio,
                  │                            aplica PRECIO_MINIMO, vende o bloquea
                  └─ ciclo banco↔mercado    → mientras haya espacio en el almacén
                                               de venta, vuelve al banco por más
           └─ caminarMina()         → vuelve caminando a la mina
```

`recnec()` es la función "de seguridad" que se llama constantemente en casi
todos los loops: detecta pantallas de carga, desconexiones, ventanas de
mantenimiento/inactividad, y si algo se traba demasiado tiempo llama a
`reiniciar_juego()` (cierra el juego, lo vuelve a abrir y reconecta).

---

## 2. Infraestructura / arranque

| Función | Línea | Qué hace |
|---|---|---|
| `class _Tee` | 25 | Redirige `print()` para que salga por consola **y** se guarde en `bot_log.txt` con timestamp. |
| `registrar_progreso()` | 58 | Actualiza el timestamp global `_ultimo_progreso`, usado por el watchdog. |
| `_watchdog()` | 62 | Hilo en segundo plano: si pasan 5 min sin que `registrar_progreso()` se llame (bot realmente trabado), fuerza `reiniciar_juego()`. |
| `_monitor_ventana()` | 79 | Hilo en segundo plano: si la ventana del juego pierde el foco 15s seguidos, la restaura y la trae al frente. |
| `_asegurar_ventana_maximizada()` | 116 | Comprueba (cada 5s) que la ventana del juego esté maximizada; si no, la maximiza. |
| `recnec()` | 142 | **La función más importante del archivo.** Se llama en casi todos los loops. Detecta: pantalla de carga colgada (>60s → reinicia), pixeles de servidor caído/mantenimiento/cuenta inactiva (reintenta login), y si la reconexión no se resuelve en 3 min, llama `reiniciar_juego()`. También dispara `_asegurar_ventana_maximizada()` periódicamente. |
| `recnec2()` | 250 | ⚠️ **Código muerto** — variante alternativa de `recnec()`, no se llama desde ningún lado. |
| `reconectar()` | 375 | ⚠️ **Código muerto** — versión antigua que cierra y reabre el juego a mano con un acceso directo; reemplazada por `reiniciar_juego()`. |
| `forzar_foco(hwnd)` | 4504 | Trae una ventana de Windows al frente aunque otra tenga el foco (bypass de la restricción de Windows). Usado por `reiniciar_juego()`. |
| `reiniciar_juego()` | 4518 | Cierra el juego (taskkill), abre el launcher, clickea JUGAR, maximiza la ventana y reintenta `recnec()`. Reintenta indefinidamente hasta lograr reconectar. Usa el flag global `_dentro_de_reiniciar` para que `recnec()` no se llame a sí misma en bucle mientras esto corre. |

## 3. Utilidades genéricas

| Función | Línea | Qué hace |
|---|---|---|
| `esperar_sala(condicion, timeout=80, ...)` | 315 | Espera (polling cada 0.2s) hasta que `condicion()` sea `True`, llamando `recnec()`/`inter()`/`any_desk()` en cada vuelta. Puede ejecutar un callback `reintento` cada 7s. |
| `inter()` | 339 | Cierra un popup de interacción/diálogo específico si aparece en pantalla. |
| `any_desk()` | 3643 | Detecta y cierra la notificación de la app AnyDesk (acceso remoto) si tapa la pantalla del juego. Se llama muy seguido (42 sitios) de forma defensiva. |
| `calcular_distancia(pos1, pos2)` | 672 | Distancia euclidiana entre dos puntos `(x,y)`. |

## 4. Detección de imágenes / templates (OpenCV)

| Función | Línea | Qué hace |
|---|---|---|
| `detectar_enemigo_sala(imagen, region, umbral)` | 349 | Busca una imagen de enemigo en una región de pantalla con `matchTemplate`. |
| `buscar_imagen_en_inventario(imagen, region, umbral)` | 450 | Igual, pero pensado para buscar dentro de ventanas/inventario (region por defecto = pantalla completa). |
| `buscar_imagen_en_pantalla(imagen, region, umbral)` | 485 | Busca una imagen en pantalla y devuelve el centro si supera el umbral. Versión de un solo template. |
| `buscar_imagen_en_pantalla2(lista_imagenes, region, umbral)` | 4193 | Igual que la anterior pero prueba una **lista** de templates en orden hasta encontrar uno; si ninguno matchea, hace un click de "limpieza" de UI y devuelve `(555,555)` como centinela de "no encontrado". |
| `_score_imagen(ruta_template, screenshot_bgr)` | 524 | Carga un template desde disco y devuelve `(score, posición)` contra un screenshot ya capturado. |
| `_score_imagen_tmpl(template_bgr, screenshot_bgr)` | 535 | Igual que la anterior pero recibe el template ya cargado en memoria (evita releer el archivo en loops calientes, como `minar()`). |

## 5. Combate

| Función | Línea | Qué hace |
|---|---|---|
| `enemigo_mas_lejano_al_aliado(img_enemigo, img_aliado, ...)` | 543 | Localiza aliado y enemigo(s) por imagen y devuelve la posición del enemigo **más lejano** al aliado. Versión de un solo template por bando. |
| `enemigo_mas_cercano_al_aliado(...)` | 614 | Igual pero devuelve el **más cercano**. |
| `enemigo_mas_cercano_al_aliado2(lista_enemigo, lista_aliado, ...)` | 852 | Igual que `enemigo_mas_cercano_al_aliado` pero acepta listas de templates (varios sprites posibles) por bando; si no encuentra algo devuelve `(555,555)` en vez de `None`. Es la que usa `pelear2()` en combate. |
| `enemigo_mas_lejano_al_aliado2(...)` | 4242 | Misma idea que la anterior, versión "más lejano" con listas de templates. |
| `pelear2()` | 946 | **Handler de combate principal.** Detecta si hay pelea activa, configura modo táctico/espectador, detecta el propio turno, y según los pixeles de los hechizos disponibles tira ataque a distancia, ataque potente, o ataques cuerpo a cuerpo/de área contra el enemigo más cercano (via `enemigo_mas_cercano_al_aliado2`). También mueve al personaje en combate usando `caminar_dofus_inteligente()` (pathfinding A\*) o `caminar3()`. Se llama desde casi todos lados (105 sitios) como chequeo defensivo de "¿hay pelea? resolvela". |
| `pelear3()` | 1628 | Variante de `pelear2()` con layout de UI de combate distinto (coordenadas distintas del círculo táctico). Usada específicamente dentro de `sala()`. |
| `vent_pelea()` | 2278 | Detecta la ventana de "resultado de combate" al terminar una pelea y la cierra. |

## 6. Movimiento / pathfinding

| Función | Línea | Qué hace |
|---|---|---|
| `caminar3(umbral, umbral2)` | 676 | Mueve al personaje hacia el aliado/objetivo en combate a base de clicks direccionales según la diferencia de posición (arriba/abajo/izquierda/derecha), con macros de clicks fijos por dirección. |
| `caminar2(umbral, umbral2)` | 2726 | ⚠️ **Código muerto** — versión anterior de `caminar3()`. Reemplazada por `caminar_dofus_inteligente()` (dice su propio docstring: *"Reemplaza a caminar2()"*). |
| `class MapaDofusRetro` | 2302 | Sistema de pathfinding con detección automática de celdas caminables: toma un screenshot de la región del mapa isométrico y clasifica cada celda como caminable/obstáculo por color (gris medio = piso, muy oscuro = obstáculo). Mantiene un diccionario `self.celdas` con lo ya escaneado. |
| `heuristica_dofus(a, b)` | 2562 | Distancia Chebyshev (usada como heurística de A\* en un grid isométrico tipo Dofus). |
| `a_star_dofus(mapa, inicio, objetivo, pm_disponibles=4)` | 2570 | Algoritmo A\* clásico sobre el grid de `MapaDofusRetro`, limitado a los puntos de movimiento (PM) disponibles del personaje. |
| `ejecutar_movimiento_dofus(camino, mapa)` | 2631 | Traduce el camino calculado por `a_star_dofus` en clicks reales sobre las celdas de pantalla. |
| `caminar_dofus_inteligente(mapa, pm_disponibles=4)` | 2648 | Orquesta las tres funciones anteriores: escanea el mapa, calcula ruta al objetivo con A\* y ejecuta el movimiento. Es el sistema de movimiento en combate "moderno", usado por `pelear2()`. |

## 7. Navegación de mapas / mina

| Función | Línea | Qué hace |
|---|---|---|
| `mapa1()` | 2878 | Secuencia de navegación tras entrar a la mina hasta llegar a "sala 1". Tiene tope de 5 min — si no lo logra, `reiniciar_juego()`. |
| `rutas()` | 2982 | ⚠️ **Código muerto** — no se llama desde ningún lado. |
| `caminarMina()` | 2989 | Punto de entrada para "volver a la mina": si no detecta la sala 1, reintenta zapear; espera (con tope 5 min) a que aparezca la sala 1 y llama `mapa1()`. Se usa como mecanismo de recuperación en varios puntos (incluida `inventario()` y el loop principal si el bot queda perdido en mapas de banco/mercado). |
| `ventana_nivel()` | 3024 | Cierra el popup de "subida de nivel" si está en pantalla. |
| `sala()` | 4340 | Maneja la sala especial de pelea/entrenamiento de minero: detecta si el personaje está ahí, resuelve el combate (con `pelear3()`) y espera diálogos con tope de tiempo. |

## 8. Minería

| Función | Línea | Qué hace |
|---|---|---|
| `recolectar(x, y)` | 3432 | Doble click sobre una veta de mineral en `(x,y)` para recolectarla. |
| `minar_original(posiciones)` | 3650 | ⚠️ **Código muerto** — primera versión de `minar()`, ya no se llama. |
| `minar(posiciones)` | 3746 | **Minería de una sala.** Por cada posición de veta: clickea, confirma por template matching que hay mineral disponible (filtrando falsos positivos de "no disponible por nivel"), lo recolecta y espera a que el color del pixel cambie (confirmación de que se extrajo). Marca como "bugeada" una veta que no resuelve en 30 intentos. Devuelve cuántos minerales recolectó. |
| `minar_ws(posiciones, sala_id, nombre_mina="")` | 4046 | Wrapper de `minar()` con watchdog por sala: si una sala da pasadas vacías repetidas (`MAX_PASADAS_VACIAS`), asume que el bot está atascado y fuerza una reorientación (`caminarMina()` + `pelear2()`). Es la función que realmente se llama en el loop principal (58 sitios). |
| `minar_2(posiciones)` | 4075 | ⚠️ **Código muerto** — otra variante de minería (por comparación de brillo de pixel en vez de template matching), no se llama. |
| `minero(p)` | 4156 | Habla con el NPC minero en una de 9 posiciones predefinidas (`p` = índice) para acceder a la sala de entrenamiento/minero, y espera (tope 3 min) a que cargue esa sala. |

## 9. Banco (depositar mineral minado)

| Función | Línea | Qué hace |
|---|---|---|
| `ir_banco()` | 3035 | Viaja al banco usando una poción de teleport ("posima bonta"), deposita el inventario minado en 3 rondas de reintento con debounce (evita el bug de "el siguiente mineral ocupa el slot antes de confirmar vacío"), alimenta a la mascota (dragopavo), y al final **llama a `ir_mercado()`** — el depósito y la venta son un solo flujo continuo. |
| `inventario()` | 3408 | Se llama en cada vuelta del loop principal: si hay pelea activa la resuelve; si el inventario está lleno, dispara `ir_banco()` y después `caminarMina()` para volver a minar. |

## 10. Mercado / venta

Estas funciones viven en la sección final del archivo (línea ~4650+) y
manejan **todo** el ciclo de ir al mercado, retirar lo no vendido, vender
con protección de precio, y volver al banco por más mineral si sobra
espacio en el almacén de venta.

| Función | Línea | Qué hace |
|---|---|---|
| `MAXIMO_SLOTS`, `CAPACIDAD_INVENTARIO` | 4659-4660 | Constantes: slots del almacén de venta y lotes máximos que carga el inventario del personaje. |
| `MINERALES_ORDEN` | ~4992 | Lista `(nombre_display, nombre_archivo)` de los minerales conocidos, en el orden en que se buscan en el banco. |
| `PRECIO_MINIMO` | ~5014 | Precio mínimo de venta por mineral — protección contra manipulación de precio (alguien lista muy barato para forzar que el bot venda regalado). Se edita a mano según el mercado real. |
| `_precio_minimo_de(nombre)` | 4891 | Busca el mínimo configurado para un nombre de mineral, tolerando errores de OCR (compara solo las primeras 4 letras). |
| `obtener_elementos_en_venta(max_intentos=3)` | 4662 | OCR del contador "en venta X/17" de la ventana de comercio. Reintenta hasta 3 veces con una región de respaldo si falla. |
| `_cambiar_mapa(click_x, click_y, nombre, check_fn, ...)` | 4692 | Clickea un punto de cambio de mapa y espera (con `_esperar_mapa`) a que el mapa destino se confirme; reintenta hasta 4 veces. |
| `_esperar_mapa(nombre, check_fn, timeout=15)` | 4707 | Espera a que `check_fn()` sea `True`, con doble confirmación (debounce) para descartar falsos positivos de un frame de transición. |
| `_es_mapa1()` / `_es_mapa2()` / `_es_mapa3()` | 4728 / 4732 / 4736 | Detectan por pixel si el personaje está en el banco (mapa1), el exterior/jardín (mapa2), o el mercado (mapa3). |
| `_esperar_mapa_conocido(timeout=10)` | 5245 | Espera a que el personaje esté en cualquiera de los 3 mapas conocidos; si no, imprime los pixeles actuales para recalibrar. |
| `_navegar_a_mercado()` | 5261 | Desde mapa1 o mapa2, encadena `_cambiar_mapa()` hasta llegar al mercado (mapa3). |
| `_ir_banco_venta()` | 4962 | Cierra la ventana de comercio y navega de vuelta al banco (mapa3→mapa2→mapa1). |
| `_lista_vacia()` | 4740 | Detecta por pixel si la lista de "mis ventas" en el mercado está vacía. |
| `retirar_minerales()` | 4833 | Retira del mercado todo lo que quedó listado de una vuelta anterior, hasta vaciar la lista o llenar el inventario. |
| `_abrir_ventana_comercio()` | 5287 | Abre la ventana de comercio en el mercado y lee cuántos espacios libres hay. |
| `leer_inventario()` | 4858 | OCR de la ventana de inventario del personaje → `{nombre: cantidad}`. |
| `leer_precio_actual(debug=False)` | 4876 | OCR del precio actual mostrado al abrir el diálogo de venta de un mineral. |
| `vender_mineral(nombre, lotes)` | 4901 | Vende un mineral: lee el precio base, calcula `precio_base - 1`, y **si ese precio es menor al `PRECIO_MINIMO` configurado, no lo vende** (devuelve `'bloqueado'` en vez de vender). Si no está bloqueado, vende lote por lote. |
| `poner_todos_en_venta(inventario, minerales_bloqueados=None)` | 4943 | Llama `vender_mineral()` para cada item del inventario; los que vuelven `'bloqueado'` se agregan al set `minerales_bloqueados` (lista negra de esta sesión de venta). |
| `abrir_banco()` | 5160 | Secuencia de clicks para abrir la ventana del banco y activar el filtro "Mineral". |
| `_clic_filtro_mineral(intentos=5, espera=1.5)` | 5134 | Busca y clickea el botón de filtro "Mineral" del banco por template matching. |
| `_buscar_todos_minerales_banco(haystack_gray)` | 5031 | Detecta de una sola pasada todos los minerales visibles en la región del banco (matriz de scores, un pico por mineral) — evita escanear uno por uno. |
| `_leer_cantidad_drag(mineral_cx, mineral_cy, nombre)` | 5100 | Arrastra un mineral del banco a un slot de referencia y lee la cantidad disponible copiándola del portapapeles del juego. |
| `_leer_portapapeles()` | 5089 | Lee el portapapeles de Windows vía `tkinter` (usado por `_leer_cantidad_drag`). |
| `_leer_imagen(path)` | 5027 | Carga una imagen en escala de grises tolerando rutas con caracteres especiales (usa `np.fromfile` + `cv2.imdecode` en vez de `cv2.imread`). |
| `sacar_minerales_banco(espacios_libres, minerales_bloqueados=None)` | 5177 | Retira minerales del banco para llevar a vender, hasta llenar `espacios_libres` o `CAPACIDAD_INVENTARIO`. Salta los minerales en `minerales_bloqueados` (lista negra por precio manipulado). |
| `_vaciar_inventario_en_banco(cantidad_items=None)` | 4743 | Deposita todo el inventario del personaje en el banco (ctrl+doble-click repetido sobre el slot de referencia, que se auto-compacta). Usada cuando el inventario se llena a mitad de un retiro del mercado, y para depositar un mineral bloqueado antes de ir por uno de reemplazo. |
| `_vaciar_banco_y_reabrir_comercio(cantidad_items=None)` | 4799 | Ciclo completo: cierra comercio → banco → deposita (`_vaciar_inventario_en_banco`) → vuelve al mercado y reabre la ventana de comercio. |
| `ir_mercado()` | 5301 | **Función principal de venta.** Navega al mercado, retira lo no vendido, vende el inventario actual (con protección de precio), y mientras haya espacio en el almacén de venta, hace ciclos banco→mercado trayendo más mineral (saltando los bloqueados, y depositando primero cualquier mineral bloqueado que haya quedado sin vender en el inventario). Tolera hasta 3 vueltas sin avance (ej. si el único mineral traído se bloqueó) antes de rendirse. |

## 11. Otros / dead code adicional

| Función | Línea | Qué hace |
|---|---|---|
| `mapab1()` | 3445 | ⚠️ **Código muerto** — ruta de navegación alternativa "sala1→mercado", solo la llama `caminarMinab()`, que también está muerta. |
| `caminarMinab()` | 3620 | ⚠️ **Código muerto** — versión alternativa de `caminarMina()`, nunca se llama. |

---

## 12. Código muerto — resumen

Funciones definidas pero **nunca alcanzables** desde el loop principal
(verificado por conteo de llamadas). Quedaron de iteraciones anteriores del
bot; no hace falta entenderlas para tocar el flujo actual, y son candidatas
a borrar si algún día se quiere limpiar el archivo:

- `recnec2()` (250)
- `reconectar()` (375)
- `caminar2()` (2726)
- `rutas()` (2982)
- `minar_original()` (3650)
- `minar_2()` (4075)
- `mapab1()` (3445) y `caminarMinab()` (3620) — se llaman entre sí pero ninguna de las dos es alcanzable desde el resto del bot.

## 13. Convención de nombres

Las funciones con prefijo `_` (ej. `_es_mapa1`, `_navegar_a_mercado`,
`_precio_minimo_de`) son helpers internos del subsistema de mercado/banco,
pensados para no llamarse directamente desde fuera de ese flujo. El resto
son funciones de "más alto nivel" que sí se invocan desde el loop principal.

## 14. Archivos relacionados

- `test_ir_mercado.py` — copia aislada de todo el subsistema de mercado/banco (secciones 9 y 10 de este documento) para poder probar `ir_mercado()` y sus dependencias sin correr el bot completo. Hay que mantenerlo sincronizado a mano cuando se toca esa parte del bot principal.
- `test_funciones.py` — carga `Minas-op.py` como módulo (sin correr el loop principal) para probar funciones sueltas de forma interactiva.
- `test_banco_templates.py` — pruebas del template matching del banco.
- `bot_log.txt` — log de ejecución (ignorado por git).

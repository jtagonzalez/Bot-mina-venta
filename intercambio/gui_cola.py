"""Interfaz gráfica para armar la cola de minerales a intercambiar.

Se invoca desde emisor.py al arrancar: se abre esta ventana, y al
confirmar "Iniciar intercambio" el mismo proceso continúa con
procesar_cola() usando la configuración guardada.

También se puede correr de forma aislada: python gui_cola.py
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun


class ColaApp:
    def __init__(self, root):
        self.root = root
        self.iniciado = False
        root.title("Configurar cola de intercambio")
        root.resizable(False, False)

        self.cola = []  # lista de dicts {"mineral": str, "cantidad": int}

        # ── capacidad de inventario del personaje ──
        frame_cap = ttk.Frame(root, padding=10)
        frame_cap.grid(row=0, column=0, sticky="ew")
        ttk.Label(frame_cap, text="Capacidad de inventario del personaje:").pack(side="left")
        self.var_capacidad = tk.StringVar()
        ttk.Entry(frame_cap, textvariable=self.var_capacidad, width=10).pack(side="left", padx=5)
        ttk.Label(frame_cap, text="(unidades máximas que puede cargar por viaje al banco)",
                  foreground="gray").pack(side="left")

        # ── posición del compañero a quien se le entrega ──
        frame_pos = ttk.Frame(root, padding=10)
        frame_pos.grid(row=1, column=0, sticky="ew")
        ttk.Label(frame_pos, text="Posición del compañero:").pack(side="left")
        self.var_posicion = tk.StringVar(value="abajo")
        ttk.Radiobutton(frame_pos, text="Arriba", variable=self.var_posicion,
                         value="arriba").pack(side="left", padx=(5, 0))
        ttk.Radiobutton(frame_pos, text="Abajo", variable=self.var_posicion,
                         value="abajo").pack(side="left", padx=(5, 0))

        # ── agregar mineral a la cola ──
        frame_add = ttk.Frame(root, padding=10)
        frame_add.grid(row=2, column=0, sticky="ew")
        ttk.Label(frame_add, text="Mineral:").pack(side="left")
        self.var_mineral = tk.StringVar(value=comun.MINERALES_DISPONIBLES[0])
        combo = ttk.Combobox(frame_add, textvariable=self.var_mineral,
                              values=comun.MINERALES_DISPONIBLES, state="readonly", width=12)
        combo.pack(side="left", padx=5)

        ttk.Label(frame_add, text="Cantidad a intercambiar:").pack(side="left", padx=(10, 0))
        self.var_cantidad = tk.StringVar()
        ttk.Entry(frame_add, textvariable=self.var_cantidad, width=10).pack(side="left", padx=5)

        ttk.Button(frame_add, text="Agregar a la cola", command=self.agregar).pack(side="left", padx=(10, 0))

        # ── tabla de la cola ──
        frame_tabla = ttk.Frame(root, padding=(10, 0, 10, 10))
        frame_tabla.grid(row=3, column=0, sticky="ew")
        self.tabla = ttk.Treeview(frame_tabla, columns=("mineral", "cantidad"),
                                   show="headings", height=8)
        self.tabla.heading("mineral", text="Mineral")
        self.tabla.heading("cantidad", text="Cantidad")
        self.tabla.column("mineral", width=150)
        self.tabla.column("cantidad", width=100)
        self.tabla.pack(side="left", fill="x", expand=True)

        ttk.Button(frame_tabla, text="Quitar seleccionado", command=self.quitar).pack(side="left", padx=(10, 0))

        # ── acciones ──
        frame_botones = ttk.Frame(root, padding=10)
        frame_botones.grid(row=4, column=0, sticky="ew")
        ttk.Button(frame_botones, text="Guardar cola", command=self.guardar).pack(side="left")
        ttk.Button(frame_botones, text="Iniciar intercambio", command=self.iniciar).pack(side="left", padx=(10, 0))

        self._cargar_config_existente()

    def _cargar_config_existente(self):
        config = comun.cargar_config()
        if config.get("capacidad_inventario"):
            self.var_capacidad.set(str(config["capacidad_inventario"]))
        if config.get("posicion_companero"):
            self.var_posicion.set(config["posicion_companero"])
        for item in config.get("cola", []):
            self.cola.append(item)
            self.tabla.insert("", "end", values=(item["mineral"], item["cantidad"]))

    def agregar(self):
        mineral = self.var_mineral.get()
        try:
            cantidad = int(self.var_cantidad.get())
        except ValueError:
            messagebox.showerror("Error", "La cantidad debe ser un número entero.")
            return
        if cantidad <= 0:
            messagebox.showerror("Error", "La cantidad debe ser mayor que 0.")
            return
        self.cola.append({"mineral": mineral, "cantidad": cantidad})
        self.tabla.insert("", "end", values=(mineral, cantidad))
        self.var_cantidad.set("")

    def quitar(self):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        for item_id in seleccion:
            idx = self.tabla.index(item_id)
            self.tabla.delete(item_id)
            del self.cola[idx]

    def _validar(self):
        try:
            capacidad = int(self.var_capacidad.get())
        except ValueError:
            messagebox.showerror("Error", "La capacidad de inventario debe ser un número entero.")
            return None
        if capacidad <= 0:
            messagebox.showerror("Error", "La capacidad de inventario debe ser mayor que 0.")
            return None
        if not self.cola:
            messagebox.showerror("Error", "Agrega al menos un mineral a la cola.")
            return None
        return {
            "capacidad_inventario": capacidad,
            "posicion_companero": self.var_posicion.get(),
            "cola": self.cola,
        }

    def guardar(self):
        config = self._validar()
        if config is None:
            return
        comun.guardar_config(config)
        messagebox.showinfo("Guardado", f"Cola guardada en {comun.CONFIG_PATH}")

    def iniciar(self):
        config = self._validar()
        if config is None:
            return
        comun.guardar_config(config)
        self.iniciado = True
        self.root.destroy()


def abrir_gui():
    """Abre la ventana de configuración de la cola y bloquea hasta que se
    cierra. Retorna True si el usuario confirmó 'Iniciar intercambio',
    False si cerró la ventana sin confirmar (para no arrancar el ciclo)."""
    root = tk.Tk()
    app = ColaApp(root)
    root.mainloop()
    return app.iniciado


if __name__ == "__main__":
    abrir_gui()

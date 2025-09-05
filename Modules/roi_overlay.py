import threading
import queue
import logging
import time
import sys

try:
    import tkinter as tk
except ImportError:
    tk = None

logger = logging.getLogger("ROIOverlay")

class ROIOverlay:
    """
    Transparent ALWAYS-ON-TOP overlay that draws a rectangular border
    around a given ROI (left, top, width, height).

    Works best on Windows. On Linux/Wayland or macOS some transparency or
    click-through features may vary.

    Usage:
        ov = ROIOverlay(border_color="#FF0000", border_width=3)
        ov.start()
        ov.update_roi((left, top, w, h))
        ov.show()
        ov.hide()
        ov.stop()
    """

    def __init__(self,
                 border_color: str = "#FF0000",
                 border_width: int = 2,
                 refresh_hz: int = 30,
                 click_through: bool = True):
        self.border_color = border_color
        self.border_width = border_width
        self.refresh_interval = 1.0 / float(refresh_hz)
        self.click_through = click_through

        self._thread = None
        self._stop_event = threading.Event()
        self._cmd_q = queue.Queue()
        self._roi = None
        self._visible = False
        self._started = False

        self._root = None
        self._canvas = None
        self._win = None
        self._rect_id = None

    # ---------------- Public API ---------------- #

    def start(self):
        if tk is None:
            logger.warning("[ROIOverlay] Tkinter not available; overlay disabled.")
            return
        if self._started:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="ROIOverlayThread", daemon=True)
        self._thread.start()
        self._started = True
        logger.info("[ROIOverlay] Overlay thread started.")

    def stop(self):
        if not self._started:
            return
        self._stop_event.set()
        self._cmd_q.put(("quit", None))
        if self._thread:
            self._thread.join(timeout=2.0)
        self._started = False
        logger.info("[ROIOverlay] Overlay thread stopped.")

    def update_roi(self, roi_tuple):
        """
        roi_tuple: (left, top, width, height)
        """
        if not self._started:
            return
        self._roi = roi_tuple
        self._cmd_q.put(("roi", roi_tuple))

    def show(self):
        if not self._started:
            return
        self._visible = True
        self._cmd_q.put(("show", None))

    def hide(self):
        if not self._started:
            return
        self._visible = False
        self._cmd_q.put(("hide", None))

    # ---------------- Internal Thread / Tk Loop ---------------- #

    def _run(self):
        try:
            self._root = tk.Tk()
            self._root.withdraw()  # We'll use a Toplevel for borderless control

            self._win = tk.Toplevel(self._root)
            self._win.overrideredirect(True)
            self._win.attributes("-topmost", True)

            # Transparent background (Windows). On other platforms it might show black.
            if sys.platform.startswith("win"):
                # Set a transparent color
                self._win.config(bg="magenta")
                try:
                    self._win.wm_attributes("-transparentcolor", "magenta")
                except Exception:
                    pass
            else:
                # Semi-transparent fallback
                try:
                    self._win.attributes("-alpha", 0.5)
                except Exception:
                    pass
                self._win.config(bg="black")

            # Attempt click-through (Windows only)
            if sys.platform.startswith("win") and self.click_through:
                try:
                    import ctypes
                    import ctypes.wintypes as wintypes
                    GWL_EXSTYLE = -20
                    WS_EX_TRANSPARENT = 0x00000020
                    WS_EX_LAYERED = 0x00080000

                    hwnd = ctypes.windll.user32.GetParent(self._win.winfo_id())
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
                    ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_TRANSPARENT | WS_EX_LAYERED)
                except Exception as e:
                    logger.debug(f"[ROIOverlay] Click-through setup failed: {e}")

            self._canvas = tk.Canvas(self._win,
                                     highlightthickness=0,
                                     bd=0,
                                     bg=self._win.cget("bg"))
            self._canvas.pack(fill="both", expand=True)

            self._root.after(10, self._process_commands)
            self._root.mainloop()
        except Exception as e:
            logger.error(f"[ROIOverlay] Exception in overlay thread: {e}")

    def _process_commands(self):
        try:
            while True:
                cmd, payload = self._cmd_q.get_nowait()
                if cmd == "quit":
                    try:
                        self._win.destroy()
                    except Exception:
                        pass
                    try:
                        self._root.destroy()
                    except Exception:
                        pass
                    return
                elif cmd == "roi":
                    self._apply_roi(payload)
                elif cmd == "show":
                    self._apply_show(True)
                elif cmd == "hide":
                    self._apply_show(False)
        except queue.Empty:
            pass

        # Periodic refresh (e.g., if we want to animate later)
        if not self._stop_event.is_set():
            self._root.after(int(self.refresh_interval * 1000), self._process_commands)

    def _apply_roi(self, roi):
        if not roi:
            return
        left, top, w, h = roi
        # Position window
        try:
            self._win.geometry(f"{w}x{h}+{left}+{top}")
        except Exception:
            return

        # Clear and redraw rectangle
        self._canvas.delete("all")
        self._rect_id = self._canvas.create_rectangle(
            self.border_width // 2,
            self.border_width // 2,
            w - self.border_width // 2,
            h - self.border_width // 2,
            outline=self.border_color,
            width=self.border_width
        )

    def _apply_show(self, visible: bool):
        try:
            if visible:
                self._win.deiconify()
            else:
                self._win.withdraw()
        except Exception:
            pass
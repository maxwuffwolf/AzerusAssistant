import threading
import logging
import time

try:
    import keyboard  # Global hotkeys; requires permissions
except ImportError:
    keyboard = None

logger = logging.getLogger("Hotkeys")

class GlobalHotkeyManager:
    def __init__(self):
        self._bindings = {}
        self._stop_event = threading.Event()
        self._thread = None
        if keyboard is None:
            logger.warning("keyboard module not installed. Global hotkeys disabled.")
        else:
            self._thread = threading.Thread(target=self._loop, name="HotkeyThread", daemon=True)
            self._thread.start()

    def register_hotkey(self, key, callback):
        if keyboard is None:
            logger.warning(f"Cannot register hotkey {key}; keyboard module missing.")
            return
        logger.info(f"Registering hotkey {key}")
        self._bindings[key.lower()] = callback

    def _loop(self):
        while not self._stop_event.is_set():
            try:
                for k, cb in list(self._bindings.items()):
                    if keyboard.is_pressed(k):
                        cb()
                        time.sleep(0.35)  # Debounce
            except Exception as e:
                logger.error(f"Hotkey loop error: {e}")
            time.sleep(0.05)

    def stop(self):
        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=2)
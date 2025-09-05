import threading

class SharedState:
    """
    Shared flags orchestrating coordination between modules.
    """
    def __init__(self):
        self._lock = threading.RLock()
        self.autoclicker_allowed = True
        self.weapon_recovery_in_progress = False

    def set_autoclicker_allowed(self, value: bool):
        with self._lock:
            self.autoclicker_allowed = value

    def is_autoclicker_allowed(self) -> bool:
        with self._lock:
            return self.autoclicker_allowed
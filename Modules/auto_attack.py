import threading
import time
import logging
from typing import Optional, Callable

try:
    import pyautogui
except ImportError:
    pyautogui = None

logger = logging.getLogger("AutoClicker")


class AutoClicker:
    """
    AutoClicker with:
      - last_click_time (for latency diagnostics)
      - early_stop_fn (checked twice per click cycle)
      - minimal sleep granularity for quick abort
    """

    def __init__(self, shared_state, button="left", clicks_per_second=10.0,
                 early_stop_fn: Optional[Callable[[], bool]] = None):
        self.shared_state = shared_state
        self.button = button
        self.clicks_per_second = clicks_per_second
        self.early_stop_fn = early_stop_fn

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_flag = False
        self._idle_event = threading.Event()
        self._idle_event.set()

        self._lock = threading.RLock()
        self._user_intended_on = False
        self.last_click_time = 0.0

    # ------------- API -------------

    def set_early_stop_fn(self, fn: Optional[Callable[[], bool]]):
        self.early_stop_fn = fn

    def user_intended_on(self) -> bool:
        return self._user_intended_on

    def set_cps(self, cps: float):
        with self._lock:
            if cps <= 0:
                raise ValueError("CPS must be > 0")
            self.clicks_per_second = cps
        logger.info(f"[AutoClicker] CPS set to {cps}")

    def is_running(self):
        return self._active_flag and self._thread and self._thread.is_alive()

    def toggle(self):
        if self.is_running():
            self._user_intended_on = False
            self.stop()
        else:
            self._user_intended_on = True
            self.start()

    def start(self):
        if self.shared_state.weapon_recovery_in_progress:
            logger.info("[AutoClicker] Start blocked (weapon recovery).")
            return
        if not self.shared_state.is_autoclicker_allowed():
            logger.info("[AutoClicker] Start blocked (shared_state disallows).")
            return
        if self.is_running():
            return
        if pyautogui is None:
            logger.error("[AutoClicker] pyautogui not installed.")
            return
        logger.info("[AutoClicker] Starting thread.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AutoClickerThread", daemon=True)
        self._active_flag = True
        self._thread.start()

    def stop(self, timeout: float = 0.6):
        if not self.is_running():
            return
        logger.info("[AutoClicker] Stopping (graceful).")
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._active_flag = False
        self._idle_event.set()
        self._flush_mouse()

    def force_stop_blocking(self, max_wait: float = 1.0):
        if not self.is_running():
            return
        logger.info("[AutoClicker] FORCE stop.")
        self._stop_event.set()
        start = time.time()
        while self._thread.is_alive() and (time.time() - start) < max_wait:
            time.sleep(0.0015)
        if self._thread.is_alive():
            logger.error("[AutoClicker] FORCE stop timeout (thread still alive).")
        self._active_flag = False
        self._idle_event.set()
        self._flush_mouse()

    def _flush_mouse(self):
        if pyautogui:
            try:
                pyautogui.mouseUp(button=self.button)
            except Exception:
                pass

    # ------------- Internal Loop -------------

    def _run(self):
        logger.debug("[AutoClicker] Loop start.")
        next_time = time.time()
        interval = 1.0 / self.clicks_per_second

        while not self._stop_event.is_set():
            if self.early_stop_fn and self.early_stop_fn():
                logger.debug("[AutoClicker] Early-stop predicate triggered (pre-loop).")
                break

            if not self.shared_state.is_autoclicker_allowed():
                if not self._idle_event.is_set():
                    self._idle_event.set()
                time.sleep(0.01)
                continue

            now = time.time()
            if now >= next_time:
                self._idle_event.clear()

                # Final gates
                if self.early_stop_fn and self.early_stop_fn():
                    self._idle_event.set()
                    break
                if not self.shared_state.is_autoclicker_allowed():
                    self._idle_event.set()
                    continue

                try:
                    pyautogui.click(button=self.button)
                    self.last_click_time = now
                except Exception as e:
                    logger.error(f"[AutoClicker] Click failed: {e}")
                    self._stop_event.set()
                    break
                finally:
                    self._idle_event.set()

                next_time = now + interval
            else:
                # Sleep tiny slices for fast abort
                time.sleep(min(0.0012, max(0.0, next_time - now)))

        self._idle_event.set()
        self._active_flag = False
        logger.debug("[AutoClicker] Loop exit.")
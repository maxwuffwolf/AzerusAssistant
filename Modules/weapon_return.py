import time
import threading
import logging
import os
from typing import Optional, Tuple

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import cv2
    import numpy as np
except ImportError:
    cv2 = None
    np = None

logger = logging.getLogger("WeaponReturn")

TRIGGER_MESSAGE = "У вас выбили оружие из рук!"


class WeaponReturnWatcher:
    """
    Weapon recovery logic with STRICT guarantee:
    Autoclicker is completely stopped (thread terminated) BEFORE inventory opens and
    remains stopped for the entire duration (open -> template search -> assign -> close).

    Only AFTER inventory is fully closed and recovery finalized the autoclicker may restart.
    """

    def __init__(
        self,
        shared_state,
        autoclicker,
        log_path: Optional[str] = None,
        weapon_template_path: str = "Assets/weapon_template.png",
        weapon_template_hotbar_path: str = "Assets/weapon_template_hotbar.png",
        inventory_key: str = "q",
        weapon_hotbar_slot_key: str = "2",
        match_threshold: float = 0.78
    ):
        self.shared_state = shared_state
        self.autoclicker = autoclicker
        self.log_path = log_path

        self.weapon_template_path = weapon_template_path
        self.weapon_template_hotbar_path = weapon_template_hotbar_path
        self.match_threshold = match_threshold

        self.inventory_key = inventory_key
        self.weapon_hotbar_slot_key = weapon_hotbar_slot_key

        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="WeaponReturnThread", daemon=True)
        self._started = False
        self.last_action = "Idle"

        self._start_thread()

    # ------------- Public API -------------

    def set_log_path(self, path: str):
        logger.info(f"[WeaponReturn] Setting log path: {path}")
        self.log_path = path

    def stop(self):
        self._stop_event.set()

    def manual_trigger(self):
        logger.info("[WeaponReturn] Manual trigger (F4).")
        self._do_recovery()

    # ------------- Internal Thread -------------

    def _start_thread(self):
        if not self._started:
            self._thread.start()
            self._started = True
            logger.debug("[WeaponReturn] Watcher thread started.")

    def _loop(self):
        last_size = 0
        logger.info("[WeaponReturn] Log watcher running.")
        while not self._stop_event.is_set():
            if self.log_path and os.path.isfile(self.log_path):
                try:
                    current_size = os.path.getsize(self.log_path)
                    if current_size < last_size:
                        logger.debug("[WeaponReturn] Log rotated; resetting pointer.")
                        last_size = 0
                    if current_size > last_size:
                        with open(self.log_path, "r", encoding="utf-8", errors="ignore") as f:
                            if last_size:
                                f.seek(last_size)
                            for raw_line in f:
                                if TRIGGER_MESSAGE in raw_line:
                                    logger.info("[WeaponReturn] Trigger message found.")
                                    self._do_recovery()
                        last_size = current_size
                except Exception as e:
                    logger.error(f"[WeaponReturn] Log read error: {e}")
            time.sleep(0.25)
        logger.info("[WeaponReturn] Log watcher stopped.")

    # ------------- Recovery Routine -------------

    def _do_recovery(self):
        if pyautogui is None:
            logger.error("[WeaponReturn] pyautogui not installed.")
            return
        if self.shared_state.weapon_recovery_in_progress:
            logger.debug("[WeaponReturn] Recovery already running; skipping.")
            return

        logger.info("[WeaponReturn] >>> Recovery START")
        self.shared_state.weapon_recovery_in_progress = True
        self.last_action = "Recovering"

        # Remember if autoclicker was active
        was_running = self.autoclicker.is_running()
        logger.debug(f"[WeaponReturn] Autoclicker active before recovery: {was_running}")

        # 1. Disable permission first (so even if start() is called elsewhere it refuses)
        self.shared_state.set_autoclicker_allowed(False)
        logger.debug("[WeaponReturn] Autoclicker allowed flag set FALSE.")

        # 2. Hard force stop if running (blocking)
        if was_running:
            self.autoclicker.force_stop_blocking(max_wait=3.0)

        # 3. Small buffer to flush queued OS events
        time.sleep(0.05)
        if pyautogui:
            try:
                pyautogui.mouseUp(button="left")
            except Exception:
                pass

        # 4. Open inventory (guaranteed no autoclick thread exists now)
        try:
            logger.info(f"[WeaponReturn] Opening inventory (key '{self.inventory_key}').")
            pyautogui.press(self.inventory_key)
            time.sleep(0.22)

            # 5. Move cursor out of way
            try:
                sw, sh = pyautogui.size()
                neutral = (sw // 2, sh // 4)
                pyautogui.moveTo(*neutral, duration=0.07)
                logger.debug(f"[WeaponReturn] Cursor moved to neutral {neutral}.")
            except Exception as e:
                logger.warning(f"[WeaponReturn] Neutral cursor move failed: {e}")

            # 6. Template search
            match_result = self._find_weapon_template()
            if match_result:
                x, y, template_type, conf = match_result
                logger.info(f"[WeaponReturn] Weapon found ({template_type}) at ({x},{y}) conf={conf:.3f}")
                try:
                    pyautogui.moveTo(x, y, duration=0.08)
                except Exception as e:
                    logger.error(f"[WeaponReturn] Move to weapon failed: {e}")
                logger.debug(f"[WeaponReturn] Assigning to slot '{self.weapon_hotbar_slot_key}'.")
                pyautogui.press(self.weapon_hotbar_slot_key)
            else:
                logger.warning("[WeaponReturn] Weapon template NOT found (inventory + hotbar).")
                self.last_action = "Template not found"

            # 7. Close inventory
            logger.info(f"[WeaponReturn] Closing inventory (key '{self.inventory_key}').")
            pyautogui.press(self.inventory_key)
            time.sleep(0.12)

            if self.last_action != "Template not found":
                self.last_action = "Recovered"
                logger.info("[WeaponReturn] >>> Recovery SUCCESS")
            else:
                logger.info("[WeaponReturn] >>> Recovery FINISHED (not found)")
        except Exception as e:
            logger.error(f"[WeaponReturn] Recovery error: {e}")
            self.last_action = f"Error: {e}"
        finally:
            # 8. Mark process end THEN allow autoclicker
            self.shared_state.weapon_recovery_in_progress = False
            self.shared_state.set_autoclicker_allowed(True)
            logger.debug("[WeaponReturn] Autoclicker allowed flag restored TRUE.")
            if was_running:
                logger.info("[WeaponReturn] Restarting autoclicker (was active before recovery).")
                self.autoclicker.start()

    # ------------- Template Matching -------------

    def _find_weapon_template(self) -> Optional[Tuple[int, int, str, float]]:
        """
        Returns (x, y, template_type, confidence) or None.
        template_type: 'inventory' | 'hotbar'
        """
        if cv2 is None or np is None:
            logger.warning("[WeaponReturn] OpenCV/numpy not installed.")
            return None
        if pyautogui is None:
            logger.warning("[WeaponReturn] pyautogui unavailable.")
            return None

        inv_exists = os.path.isfile(self.weapon_template_path)
        hot_exists = os.path.isfile(self.weapon_template_hotbar_path)
        if not inv_exists and not hot_exists:
            logger.warning("[WeaponReturn] Both weapon templates missing.")
            return None

        try:
            screenshot = pyautogui.screenshot()
            scr = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error(f"[WeaponReturn] Screenshot failure: {e}")
            return None

        best = None  # (conf, x, y, type)

        if inv_exists:
            r = self._match_template(scr, self.weapon_template_path, "inventory")
            if r:
                conf, cx, cy, t = r
                best = (conf, cx, cy, t)
                logger.debug(f"[WeaponReturn] Inventory match conf={conf:.3f}")

        if hot_exists:
            r = self._match_template(scr, self.weapon_template_hotbar_path, "hotbar")
            if r:
                conf, cx, cy, t = r
                logger.debug(f"[WeaponReturn] Hotbar match conf={conf:.3f}")
                if best is None or conf > best[0]:
                    best = (conf, cx, cy, t)

        if best:
            conf, x, y, ttype = best
            return x, y, ttype, conf
        return None

    def _match_template(self, screen_bgr, template_path: str, template_type: str):
        try:
            tpl = cv2.imread(template_path, cv2.IMREAD_COLOR)
            if tpl is None:
                logger.warning(f"[WeaponReturn] Cannot read template: {template_path}")
                return None
            res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= self.match_threshold:
                th, tw = tpl.shape[:2]
                center = (max_loc[0] + tw // 2, max_loc[1] + th // 2)
                logger.debug(f"[WeaponReturn] Template {template_type} matched at {center} conf={max_val:.3f}")
                return (max_val, center[0], center[1], template_type)
            else:
                logger.debug(f"[WeaponReturn] Template {template_type} below threshold ({max_val:.3f} < {self.match_threshold})")
        except Exception as e:
            logger.error(f"[WeaponReturn] Template match error ({template_type}): {e}")
        return None
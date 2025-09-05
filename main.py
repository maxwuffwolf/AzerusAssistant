import logging
from GUI import AzerusAppGUI
from Modules.auto_attack import AutoClicker
from Modules.weapon_return import WeaponReturnWatcher
from Modules.blood_curse import BloodCurseWatcher
from Modules.hotkeys import GlobalHotkeyManager
from Modules.shared_state import SharedState

def configure_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(threadName)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S"
    )
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("cv2").setLevel(logging.WARNING)
    logging.getLogger("pytesseract").setLevel(logging.WARNING)

def main():
    configure_logging()
    logger = logging.getLogger("main")

    shared_state = SharedState()

    autoclicker = AutoClicker(shared_state=shared_state)
    weapon_return = WeaponReturnWatcher(shared_state=shared_state, autoclicker=autoclicker)
    blood_curse = BloodCurseWatcher(shared_state=shared_state, autoclicker=autoclicker)

    hotkeys = GlobalHotkeyManager()
    hotkeys.register_hotkey("F6", autoclicker.toggle)
    hotkeys.register_hotkey("F4", weapon_return.manual_trigger)

    app = AzerusAppGUI(
        shared_state=shared_state,
        autoclicker=autoclicker,
        weapon_return=weapon_return,
        blood_curse=blood_curse,
        hotkeys=hotkeys
    )

    logger.info("Starting Azerus Assistant UI")
    app.run()

    logger.info("Shutting down modules...")
    weapon_return.stop()
    blood_curse.stop()
    autoclicker.stop()
    hotkeys.stop()
    logger.info("Exited cleanly.")

if __name__ == "__main__":
    main()
import logging
import tkinter as tk
from tkinter import ttk, filedialog
from queue import Queue, Empty
import threading
import time

from Modules.log_gui_handler import TkinterQueueHandler

logger = logging.getLogger("GUI")

class AzerusAppGUI:
    POLL_INTERVAL_MS = 120

    def __init__(self, shared_state, autoclicker, weapon_return, blood_curse, hotkeys):
        self.shared_state = shared_state
        self.autoclicker = autoclicker
        self.weapon_return = weapon_return
        self.blood_curse = blood_curse
        self.hotkeys = hotkeys

        self.root = tk.Tk()
        self.root.title("Azerus Assistant")
        self.root.geometry("1000x640")

        self.log_queue = Queue()
        self._install_logging_handler()

        self._build_layout()
        self._schedule_poll()
        self._schedule_status_refresh()

    def _install_logging_handler(self):
        handler = TkinterQueueHandler(self.log_queue)
        handler.setLevel(logging.INFO)
        logging.getLogger().addHandler(handler)

    def _build_layout(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Left controls
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=1)

        # Autoclicker group
        ac_group = ttk.LabelFrame(left_frame, text="Auto Attack (F6)")
        ac_group.pack(fill=tk.X, pady=4)
        self.ac_status_var = tk.StringVar(value="OFF")
        ttk.Label(ac_group, text="Status:").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Label(ac_group, textvariable=self.ac_status_var, foreground="red").grid(row=0, column=1, sticky="w")
        ttk.Button(ac_group, text="Toggle (F6)", command=self.autoclicker.toggle).grid(row=1, column=0, columnspan=2, pady=4, padx=4, sticky="ew")
        ttk.Label(ac_group, text="CPS:").grid(row=2, column=0, sticky="e")
        self.cps_var = tk.DoubleVar(value=self.autoclicker.clicks_per_second)
        cps_entry = ttk.Entry(ac_group, textvariable=self.cps_var, width=6)
        cps_entry.grid(row=2, column=1, sticky="w", padx=4)
        ttk.Button(ac_group, text="Apply CPS", command=self._apply_cps).grid(row=3, column=0, columnspan=2, sticky="ew", padx=4, pady=4)

        # Weapon Return group
        wr_group = ttk.LabelFrame(left_frame, text="Weapon Return (F4)")
        wr_group.pack(fill=tk.X, pady=4)
        self.wr_status_var = tk.StringVar(value="Idle")
        ttk.Label(wr_group, text="Last action:").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(wr_group, textvariable=self.wr_status_var).grid(row=0, column=1, sticky="w")
        ttk.Button(wr_group, text="Manual Trigger (F4)", command=self.weapon_return.manual_trigger).grid(row=1, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(wr_group, text="Select Log File", command=self._choose_log).grid(row=2, column=0, columnspan=2, sticky="ew", padx=4, pady=2)
        self.log_path_var = tk.StringVar(value=self.weapon_return.log_path or "Not selected")
        ttk.Label(wr_group, textvariable=self.log_path_var, wraplength=260, foreground="gray").grid(row=3, column=0, columnspan=2, sticky="w", padx=4, pady=2)

        # Blood Curse group
        bc_group = ttk.LabelFrame(left_frame, text="Blood Curse Monitor")
        bc_group.pack(fill=tk.X, pady=4)
        self.bc_active_var = tk.StringVar(value="Not Detected")
        ttk.Label(bc_group, text="Status:").grid(row=0, column=0, sticky="w", padx=4)
        ttk.Label(bc_group, textvariable=self.bc_active_var).grid(row=0, column=1, sticky="w")
        ttk.Button(bc_group, text="Start", command=self.blood_curse.start).grid(row=1, column=0, sticky="ew", padx=4, pady=2)
        ttk.Button(bc_group, text="Stop", command=self.blood_curse.stop).grid(row=1, column=1, sticky="ew", padx=4, pady=2)

        # Right logs
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=3)

        log_frame = ttk.LabelFrame(right_frame, text="Logs")
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, height=25, state="disabled", wrap="none", background="#111", foreground="#ddd")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.log_text.tag_configure("INFO", foreground="#b3e5fc")
        self.log_text.tag_configure("ERROR", foreground="#ff8a80")
        self.log_text.tag_configure("WARNING", foreground="#ffd54f")
        self.log_text.tag_configure("DEBUG", foreground="#757575")
        self.autoscroll = tk.BooleanVar(value=True)
        ttk.Checkbutton(log_frame, text="Auto-scroll", variable=self.autoscroll).pack(anchor="w", padx=4)

        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self.status_var, anchor="w").pack(fill=tk.X)

    def _apply_cps(self):
        try:
            cps = float(self.cps_var.get())
            self.autoclicker.set_cps(cps)
            logging.info(f"Updated clicks per second to {cps}")
        except ValueError:
            logging.error("Invalid CPS value")

    def _choose_log(self):
        path = filedialog.askopenfilename(title="Select Minecraft log file")
        if path:
            self.weapon_return.set_log_path(path)
            self.log_path_var.set(path)

    def _schedule_poll(self):
        self.root.after(self.POLL_INTERVAL_MS, self._poll_logs)

    def _poll_logs(self):
        try:
            while True:
                record = self.log_queue.get_nowait()
                self._append_log(record)
        except Empty:
            pass
        self._schedule_poll()

    def _append_log(self, record):
        self.log_text.configure(state="normal")
        tag = record.levelname
        self.log_text.insert("end", record.message + "\n", tag)
        if self.autoscroll.get():
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _schedule_status_refresh(self):
        self.root.after(500, self._refresh_status)

    def _refresh_status(self):
        self.ac_status_var.set("ON" if self.autoclicker.is_running() else "OFF")
        self.ac_status_var.set(self.ac_status_var.get())
        color = "green" if self.autoclicker.is_running() else "red"
        # Change color dynamically
        for tag in self.log_text.tag_names():
            pass
        self.wr_status_var.set(self.weapon_return.last_action)
        self.bc_active_var.set("Active" if self.blood_curse.curse_active else "Not Detected")

        self._schedule_status_refresh()

    def _on_close(self):
        self.status_var.set("Closing...")
        self.root.after(50, self.root.destroy)

    def run(self):
        self.root.mainloop()
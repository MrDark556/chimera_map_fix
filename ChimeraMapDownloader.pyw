#!/usr/bin/env python3
# Build as --windowed. No Command Prompt is shown.

from pathlib import Path
import configparser
import queue
import os
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk

import chimera_hybrid_downloader as proxy

VERSION = "3.6.1"
STATE_DIR = proxy.BASE_DIR
CONFIG_FILE = STATE_DIR / "launcher_config.ini"
LOG_FILE = STATE_DIR / "launcher.log"

def log(message):
    try:
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass

def show_error(body):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("Chimera Map Downloader", body, parent=root)
        root.destroy()
    except Exception:
        log("ERROR DIALOG: " + str(body))

def load_config():
    cfg = configparser.ConfigParser()
    if CONFIG_FILE.exists():
        try:
            cfg.read(CONFIG_FILE, encoding="utf-8")
        except Exception as e:
            log(f"Config read failed: {e}")
    if not cfg.has_section("launcher"):
        cfg.add_section("launcher")
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            cfg.write(f)
    except Exception as e:
        log(f"Config save failed: {e}")

def valid_halo(path):
    try:
        p = Path(path)
        return p.is_file() and p.name.lower() == "haloce.exe"
    except Exception:
        return False

def release_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

def launcher_halo_path():
    """Return haloce.exe beside the launcher EXE/source."""
    return release_dir() / "haloce.exe"


def standard_halo_paths():
    """Return common Halo Custom Edition install locations."""
    paths = []

    pf86 = os.environ.get("ProgramFiles(x86)")
    pf = os.environ.get("ProgramFiles")

    if pf86:
        paths.append(
            Path(pf86) / "Microsoft Games" / "Halo Custom Edition" / "haloce.exe"
        )
    if pf:
        paths.append(
            Path(pf) / "Microsoft Games" / "Halo Custom Edition" / "haloce.exe"
        )

    for drive in ("C:", "D:", "E:", "F:"):
        root = Path(drive + "\\")
        paths.extend([
            root / "Halo Custom Edition" / "haloce.exe",
            root / "Games" / "Halo Custom Edition" / "haloce.exe",
            root / "Microsoft Games" / "Halo Custom Edition" / "haloce.exe",
        ])

    unique = []
    seen = set()
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def save_halo_path(path):
    cfg = load_config()
    cfg.set("launcher", "halo_exe", str(Path(path).resolve()))
    save_config(cfg)


def ask_to_confirm_detected_halo(path):
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        answer = messagebox.askyesno(
            "Chimera Map Downloader",
            "Halo Custom Edition was found here:\n\n"
            f"{path}\n\n"
            "Is this the Halo CE installation you want to use?\n\n"
            "Choose No if you want to locate a different haloce.exe.",
            parent=root,
        )
        root.destroy()
        return bool(answer)
    except Exception as e:
        log(f"Confirmation dialog failed: {type(e).__name__}: {e}")
        return False


def browse_for_halo():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)

        messagebox.showinfo(
            "Chimera Map Downloader",
            "Halo Custom Edition could not be confirmed automatically.\n\n"
            "Please locate your Halo CE installation and select haloce.exe.\n\n"
            "Portable Halo CE installations are fully supported.",
            parent=root,
        )

        selected = filedialog.askopenfilename(
            parent=root,
            title="Select your Halo Custom Edition haloce.exe",
            filetypes=[
                ("Halo Custom Edition", "haloce.exe"),
                ("Executable files", "*.exe"),
            ],
        )

        if not selected:
            root.destroy()
            return None

        if not valid_halo(selected):
            messagebox.showerror(
                "Chimera Map Downloader",
                "The selected file is not haloce.exe.\n\n"
                "Please select the original Halo Custom Edition haloce.exe file.",
                parent=root,
            )
            root.destroy()
            return None

        root.destroy()
        selected_path = Path(selected).resolve()
        save_halo_path(selected_path)
        log(f"User selected Halo CE: {selected_path}")
        return selected_path

    except Exception as e:
        log(f"File picker failed: {type(e).__name__}: {e}")
        return None


def find_halo():
    # 1. Portable/same-folder install always wins over stale saved paths.
    beside_launcher = launcher_halo_path()
    if valid_halo(beside_launcher):
        resolved = beside_launcher.resolve()
        save_halo_path(resolved)
        log(f"Halo CE found beside launcher: {resolved}")
        return resolved

    # 2. Previously confirmed location.
    cfg = load_config()
    saved = cfg.get("launcher", "halo_exe", fallback="").strip()

    if saved and valid_halo(saved):
        resolved = Path(saved).resolve()
        log(f"Using saved Halo CE location: {resolved}")
        return resolved

    if saved:
        log("Saved Halo CE location is no longer valid; searching again.")

    # 3. Search common locations, but ask before using one.
    for candidate in standard_halo_paths():
        if not valid_halo(candidate):
            continue

        resolved = candidate.resolve()
        log(f"Possible Halo CE installation found: {resolved}")

        if ask_to_confirm_detected_halo(resolved):
            save_halo_path(resolved)
            log(f"User confirmed Halo CE location: {resolved}")
            return resolved

        log("User rejected detected Halo CE location; opening manual picker.")
        return browse_for_halo()

    # 4. Nothing found: manual selection.
    return browse_for_halo()

def port_open():
    try:
        with socket.create_connection((proxy.HOST, proxy.PORT), timeout=0.4):
            return True
    except OSError:
        return False

def start_downloader():
    # Respect a downloader the user already started.
    if port_open():
        log(
            f"{proxy.HOST}:{proxy.PORT} already active; "
            "using existing downloader."
        )
        return None, None, False

    server = proxy.ThreadingHTTPServer((proxy.HOST, proxy.PORT), proxy.Handler)

    # Active map requests should not prevent the EXE from exiting after Halo.
    server.daemon_threads = True

    thread = threading.Thread(
        target=server.serve_forever,
        name="chimera-downloader-server",
        daemon=True,
    )
    thread.start()

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if port_open():
            log(
                f"Downloader started at "
                f"http://{proxy.HOST}:{proxy.PORT}/"
            )
            return server, thread, True
        time.sleep(0.05)

    try:
        server.shutdown()
        server.server_close()
    except Exception:
        pass

    raise RuntimeError("Downloader did not become ready within 5 seconds.")

def stop_downloader(server, thread):
    if server is None:
        return

    log("Halo closed; stopping downloader.")

    try:
        server.shutdown()
    except Exception as e:
        log(f"Shutdown warning: {e}")

    try:
        server.server_close()
    except Exception as e:
        log(f"Close warning: {e}")

    if thread is not None:
        try:
            thread.join(timeout=2)
        except Exception:
            pass


PROGRESS_EVENTS = queue.Queue()

def receive_progress_event(event):
    try:
        PROGRESS_EVENTS.put_nowait(event)
    except Exception:
        pass

class FallbackProgressWindow:
    def __init__(self, root):
        self.root = root
        self.window = tk.Toplevel(root)
        self.window.withdraw()
        self.window.title("Chimera Map Downloader")
        self.window.resizable(False, False)

        try:
            self.window.attributes("-topmost", True)
        except Exception:
            pass

        try:
            self.window.wm_attributes("-toolwindow", True)
        except Exception:
            pass

        self.window.protocol("WM_DELETE_WINDOW", lambda: None)

        frame = ttk.Frame(self.window, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")

        self.title_var = tk.StringVar(value="Downloading custom map")
        self.map_var = tk.StringVar(value="")
        self.source_var = tk.StringVar(value="")
        self.stage_var = tk.StringVar(value="")
        self.detail_var = tk.StringVar(value="")

        ttk.Label(
            frame,
            textvariable=self.title_var,
            font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            frame,
            textvariable=self.map_var,
            font=("Segoe UI", 10),
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ttk.Label(
            frame,
            textvariable=self.source_var,
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        ttk.Label(
            frame,
            textvariable=self.stage_var,
        ).grid(row=3, column=0, sticky="w", pady=(6, 4))

        self.bar = ttk.Progressbar(
            frame,
            orient="horizontal",
            mode="indeterminate",
            length=390,
        )
        self.bar.grid(row=4, column=0, sticky="ew")

        ttk.Label(
            frame,
            textvariable=self.detail_var,
        ).grid(row=5, column=0, sticky="w", pady=(5, 0))

        self.visible = False
        self.indeterminate_running = False
        self.transfer_started = None
        self.transfer_start_bytes = 0
        self.hide_job = None

    def position_bottom_right(self):
        self.window.update_idletasks()
        width = self.window.winfo_reqwidth()
        height = self.window.winfo_reqheight()
        screen_w = self.window.winfo_screenwidth()
        screen_h = self.window.winfo_screenheight()
        x = max(10, screen_w - width - 28)
        y = max(10, screen_h - height - 70)
        self.window.geometry(f"+{x}+{y}")

    def show(self):
        if self.hide_job is not None:
            try:
                self.root.after_cancel(self.hide_job)
            except Exception:
                pass
            self.hide_job = None

        if not self.visible:
            self.position_bottom_right()
            self.window.deiconify()
            self.visible = True

    def hide(self):
        self.stop_indeterminate()
        self.window.withdraw()
        self.visible = False
        self.hide_job = None

    def stop_indeterminate(self):
        if self.indeterminate_running:
            try:
                self.bar.stop()
            except Exception:
                pass
            self.indeterminate_running = False

    def set_indeterminate(self):
        self.stop_indeterminate()
        self.bar.configure(mode="indeterminate", maximum=100)
        self.bar.start(12)
        self.indeterminate_running = True

    def set_determinate(self, percent):
        self.stop_indeterminate()
        self.bar.configure(mode="determinate", maximum=100)
        self.bar["value"] = max(0.0, min(100.0, percent))

    def reset_transfer_clock(self, downloaded=0):
        self.transfer_started = time.monotonic()
        self.transfer_start_bytes = int(downloaded or 0)

    @staticmethod
    def format_bytes(value):
        value = float(value or 0)
        mib = value / (1024 * 1024)
        if mib >= 1024:
            return f"{mib / 1024:.2f} GB"
        return f"{mib:.1f} MB"

    def handle(self, event):
        action = event.get("action", "update")
        map_name = event.get("map", "")
        source = event.get("source", "")
        stage = event.get("stage", "")
        downloaded = int(event.get("downloaded") or 0)
        total = event.get("total")
        total = int(total) if total else None

        if event.get("reset_transfer"):
            self.reset_transfer_clock(downloaded)

        self.map_var.set(f"Map: {map_name}")
        self.source_var.set(f"Source: {source}")
        self.stage_var.set(stage)

        if action in ("show", "update"):
            self.show()

            # A real byte transfer with known total -> percentage.
            if stage.lower().startswith("download") and total and total > 0:
                percent = downloaded * 100.0 / total
                self.set_determinate(percent)

                if self.transfer_started is None:
                    self.reset_transfer_clock(downloaded)

                elapsed = max(0.001, time.monotonic() - self.transfer_started)
                transferred_since_start = max(
                    0, downloaded - self.transfer_start_bytes
                )
                speed = transferred_since_start / elapsed

                detail = (
                    f"{self.format_bytes(downloaded)} / "
                    f"{self.format_bytes(total)}"
                )

                if speed > 128 * 1024:
                    detail += f"   •   {self.format_bytes(speed)}/s"
                    remaining = max(0, total - downloaded)
                    eta = remaining / speed if speed > 0 else 0
                    if eta >= 1:
                        if eta >= 60:
                            detail += f"   •   ~{eta / 60:.1f} min left"
                        else:
                            detail += f"   •   ~{eta:.0f}s left"

                self.detail_var.set(detail)

            elif stage.lower().startswith("download") and downloaded > 0:
                self.set_indeterminate()

                if self.transfer_started is None:
                    self.reset_transfer_clock(downloaded)

                elapsed = max(0.001, time.monotonic() - self.transfer_started)
                transferred_since_start = max(
                    0, downloaded - self.transfer_start_bytes
                )
                speed = transferred_since_start / elapsed

                detail = f"{self.format_bytes(downloaded)} downloaded"
                if speed > 128 * 1024:
                    detail += f"   •   {self.format_bytes(speed)}/s"
                self.detail_var.set(detail)

            else:
                # Searching / extracting / validating cannot have a meaningful
                # percentage, so use an animated bar.
                self.set_indeterminate()
                self.detail_var.set("Please wait...")

        elif action == "complete":
            self.show()
            self.set_determinate(100)
            self.detail_var.set("Map is ready.")
            self.hide_job = self.root.after(1200, self.hide)

        elif action == "error":
            self.show()
            self.stop_indeterminate()
            self.bar.configure(mode="determinate", maximum=100)
            self.bar["value"] = 0
            self.detail_var.set("Trying to return control to Halo...")
            self.hide_job = self.root.after(1800, self.hide)

def main():
    log("============================================================")
    log(f"Chimera Map Downloader v{VERSION} starting")
    log(f"State directory: {STATE_DIR}")

    halo = find_halo()
    if halo is None:
        show_error(
            "No valid haloce.exe was selected.\n\n"
            "Keep your original haloce.exe and place the map downloader "
            "beside it, or run the launcher again and select the correct "
            "Halo Custom Edition executable."
        )
        return 1

    server = None
    thread = None
    owned = False

    try:
        server, thread, owned = start_downloader()
    except Exception as e:
        log(f"Downloader startup failed: {type(e).__name__}: {e}")
        show_error(
            "The background map downloader could not start.\n\n"
            f"{e}\n\n"
            f"Logs are stored in:\n{STATE_DIR}"
        )
        return 2

    # Install the UI callback only for the downloader instance owned by this
    # launcher. Normal HaloNet downloads never emit fallback UI events.
    proxy.set_progress_callback(receive_progress_event)

    try:
        halo_process = subprocess.Popen(
            [str(halo)] + sys.argv[1:],
            cwd=str(halo.parent),
        )
        log(f"Launched Halo CE PID {halo_process.pid}: {halo}")
    except Exception as e:
        proxy.set_progress_callback(None)
        if owned:
            stop_downloader(server, thread)
        log(f"Halo launch failed: {type(e).__name__}: {e}")
        show_error(f"Halo Custom Edition could not start.\n\n{e}")
        return 3

    root = tk.Tk()
    root.withdraw()
    progress_window = FallbackProgressWindow(root)

    halo_exit_code = {"value": None}

    def poll_progress():
        try:
            while True:
                event = PROGRESS_EVENTS.get_nowait()
                progress_window.handle(event)
        except queue.Empty:
            pass

        if halo_exit_code["value"] is None:
            root.after(100, poll_progress)

    def poll_halo():
        code = halo_process.poll()
        if code is None:
            root.after(250, poll_halo)
            return

        halo_exit_code["value"] = code
        try:
            progress_window.hide()
        except Exception:
            pass
        root.quit()

    root.after(50, poll_progress)
    root.after(250, poll_halo)

    try:
        root.mainloop()
    finally:
        try:
            root.destroy()
        except Exception:
            pass

        proxy.set_progress_callback(None)

        log(
            f"Halo CE PID {halo_process.pid} exited "
            f"with code {halo_exit_code['value']}."
        )

        if owned:
            stop_downloader(server, thread)

    log(f"Chimera Map Downloader v{VERSION} stopped")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

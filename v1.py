import os, csv, sys, time, threading
from collections import deque
from datetime import datetime
import tkinter as tk
import matplotlib.pyplot as plt
from pynput import mouse, keyboard

ROLLING          = 7
SAMPLE           = 0.5
session_start_dt = None

events         = deque()
apm_history    = []
recording      = False
lock           = threading.Lock()
mouse_listener = None
kbd_listener   = None
held_keys      = set()


def _add():
    if recording:
        with lock:
            events.append(time.time())

def on_click(x, y, btn, pressed):
    if pressed: _add()

def on_key(key):
    if key not in held_keys:
        held_keys.add(key)
        _add()

def on_release(key):
    held_keys.discard(key)

def calc_apm():
    now = time.time()
    with lock:
        while events and events[0] < now - ROLLING:
            events.popleft()
        return len(events) * 60.0 / ROLLING

def sampler():
    while recording:
        apm = calc_apm()
        with lock:
            apm_history.append((datetime.now(), apm))
        time.sleep(SAMPLE)

def start(window=7):
    global recording, mouse_listener, kbd_listener, ROLLING, session_start_dt
    if recording: return
    ROLLING          = window
    session_start_dt = datetime.now()
    held_keys.clear()
    with lock:
        events.clear(); apm_history.clear()
    recording = True
    mouse_listener = mouse.Listener(on_click=on_click)
    kbd_listener   = keyboard.Listener(on_press=on_key, on_release=on_release)
    mouse_listener.start()
    kbd_listener.start()
    threading.Thread(target=sampler, daemon=True).start()

def stop():
    global recording, mouse_listener, kbd_listener
    if not recording: return
    recording = False
    time.sleep(0.3)
    mouse_listener.stop(); mouse_listener = None
    kbd_listener.stop();   kbd_listener   = None
    save_and_plot()

def save_and_plot():
    with lock:
        hist = list(apm_history)
    if not hist: return
    subdir = os.path.join("saves", f"{ROLLING}s") if ROLLING in (7, 35) else "saves"
    os.makedirs(subdir, exist_ok=True)
    path = os.path.join(subdir, f"{ROLLING}s_" + session_start_dt.strftime("%Y-%m-%d_%H-%M-%S") + ".csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["datetime", "apm"])
        for dt, a in hist:
            w.writerow([dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3], f"{a:.2f}"])
    print(path)
    t0    = hist[0][0].timestamp()
    times = [(dt.timestamp() - t0) for dt, _ in hist]
    apms  = [a for _, a in hist]
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(times, apms, color="#1e90ff", linewidth=1.5)
    ax.fill_between(times, apms, alpha=0.2, color="#1e90ff")
    ax.set_title(session_start_dt.strftime("%Y-%m-%d %H:%M:%S"))
    ax.set_xlabel("Time (s)"); ax.set_ylabel("APM"); ax.set_ylim(bottom=0)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    plt.show()

def cmd_loop():
    while True:
        try:
            cmd = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if cmd == "/start":
            start(7)
        elif cmd == "/start2":
            start(35)
        elif cmd.startswith("/start "):
            try:
                start(int(cmd.split()[1]))
            except (ValueError, IndexError):
                pass
        elif cmd == "/stop":
            stop()
        elif cmd in ("/quit", "/exit"):
            if recording: stop()
            os._exit(0)

def tick(label, win, bg, root):
    if recording:
        with lock:
            cur = apm_history[-1][1] if apm_history else 0.0
        label.config(text=str(int(cur)))
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        bg.geometry(f"{w}x{h}+30+30")
        bg.deiconify()
        win.deiconify()
    else:
        win.withdraw()
        bg.withdraw()
    root.after(100, tick, label, win, bg, root)

def main():
    import ctypes
    user32    = ctypes.windll.user32
    GWL_EXSTYLE       = -20
    WS_EX_NOACTIVATE  = 0x08000000
    WS_EX_TRANSPARENT = 0x00000020
    SWP_NOMOVE = 0x0002; SWP_NOSIZE = 0x0001; SWP_NOACTIVATE = 0x0010

    root = tk.Tk()
    root.withdraw()

    # 20% opaque dark background box
    bg = tk.Toplevel(root)
    bg.overrideredirect(True)
    bg.geometry("+30+30")
    bg.configure(bg="#111111")
    bg.wm_attributes("-topmost", True)
    bg.wm_attributes("-alpha", 0.2)
    bg.withdraw()

    # 100% opaque text on transparent background
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.geometry("+30+30")
    win.wm_attributes("-topmost", True)
    win.wm_attributes("-transparentcolor", "black")
    win.configure(bg="black")
    label = tk.Label(win, text="0", font=("Lucida Console", 42, "bold"),
                     fg="#FF6C32", bg="black", padx=6, pady=2)
    label.pack()
    win.withdraw()
    win.update()

    for hwnd in (win.winfo_id(), bg.winfo_id()):
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT)

    win_hwnd = win.winfo_id()
    bg_hwnd  = bg.winfo_id()

    def keep_topmost():
        while True:
            # bg first so win ends up above it
            user32.SetWindowPos(bg_hwnd,  -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            user32.SetWindowPos(win_hwnd, -1, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
            time.sleep(0.5)
    threading.Thread(target=keep_topmost, daemon=True).start()

    threading.Thread(target=cmd_loop, daemon=True).start()
    root.after(100, tick, label, win, bg, root)
    root.mainloop()

if __name__ == "__main__":
    main()

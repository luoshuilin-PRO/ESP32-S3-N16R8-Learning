"""Controlled HID test: clicks land only inside a temporary full-screen window."""
import ctypes
from pathlib import Path
import subprocess
import tkinter as tk

from PIL import Image, ImageTk


BASE = Path(__file__).resolve().parent
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
user32 = ctypes.windll.user32


class Point(ctypes.Structure):
    _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]


old_cursor = Point()
user32.GetCursorPos(ctypes.byref(old_cursor))
root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.geometry(f'{user32.GetSystemMetrics(0)}x{user32.GetSystemMetrics(1)}+0+0')
root.configure(background='white')
sample = BASE.parent / 'material-capture/samples/positive/20261009_101120_177894.png'
with Image.open(sample) as source:
    photo = ImageTk.PhotoImage(source.convert('RGB'))
patch = tk.Label(root, image=photo, borderwidth=0, highlightthickness=0)
patch.place(x=911, y=595)
heartbeat = tk.Canvas(root, width=2, height=2, highlightthickness=0)
heartbeat.place(x=20, y=20)
pixel = heartbeat.create_rectangle(0, 0, 2, 2, fill='black', outline='')
phase = [False]


def animate():
    phase[0] = not phase[0]
    heartbeat.itemconfigure(pixel, fill='white' if phase[0] else 'black')
    root.after(16, animate)


root.after(16, animate)
clicks = []
counts = {}
root.bind('<ButtonPress-1>', lambda event: clicks.append(1))
root.update()
root.focus_force()
root.lift()
window_hwnd = user32.GetAncestor(root.winfo_id(), 2)
user32.SetForegroundWindow(window_hwnd)
user32.SetCursorPos(1000, 800)
root.update()
if user32.GetForegroundWindow() != window_hwnd:
    root.destroy()
    user32.SetCursorPos(old_cursor.x, old_cursor.y)
    raise RuntimeError('test window did not gain foreground focus; no clicks sent')

program = BASE / 'build/Release/vision_dxgi.exe'
process = subprocess.Popen([str(program), '--click', '--port', 'COM4', '--seconds', '6'],
                           cwd=BASE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, creationflags=subprocess.CREATE_NO_WINDOW)


def hide():
    patch.place_forget()
    root.configure(background='white')
    root.update_idletasks()
    counts['first'] = len(clicks)


def show():
    counts['clear'] = len(clicks)
    patch.place(x=950, y=599)
    root.update_idletasks()


def hide_again():
    patch.place_forget()
    root.update_idletasks()
    counts['second'] = len(clicks)


def finish():
    if process.poll() is None:
        root.after(100, finish)
    else:
        root.destroy()


root.after(1800, hide)
root.after(2800, show)
root.after(4200, hide_again)
root.after(6500, finish)
try:
    root.mainloop()
    output, _ = process.communicate(timeout=2)
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=2)
    user32.SetCursorPos(old_cursor.x, old_cursor.y)
print(output)
print(f'Click counts: {counts}; final={len(clicks)}')
assert process.returncode == 0
assert 'HIT new_pixels=0 old_pixels=110' in output
assert 'HIT new_pixels=110 old_pixels=110' in output
assert output.count('VC1 ACTIVE ACK') >= 2 and output.count('VC1 STOP ACK') >= 2
assert counts['first'] > 0 and counts['clear'] <= counts['first'] + 1
assert counts['second'] > counts['clear']

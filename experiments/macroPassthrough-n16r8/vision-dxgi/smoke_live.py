"""Desktop-only integration check: show a saved red-name crop, then remove it."""
import ctypes
from pathlib import Path
import subprocess
import tkinter as tk

from PIL import Image, ImageTk


BASE = Path(__file__).resolve().parent
ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
root = tk.Tk()
root.overrideredirect(True)
root.attributes('-topmost', True)
root.geometry('16x21+950+599')
sample = BASE.parent / 'material-capture/samples/positive/20261009_101120_177894.png'
with Image.open(sample) as source:
    photo = ImageTk.PhotoImage(source.convert('RGB'))
tk.Label(root, image=photo, borderwidth=0, highlightthickness=0).pack()
root.update()
program = BASE / 'build/Release/vision_dxgi.exe'
process = subprocess.Popen([str(program), '--seconds', '4'], cwd=BASE,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
root.after(1500, root.destroy)
root.mainloop()
output, _ = process.communicate(timeout=10)
print(output)
assert process.returncode == 0 and 'HIT ' in output and 'CLEAR ' in output

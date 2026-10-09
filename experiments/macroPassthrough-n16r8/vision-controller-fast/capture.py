"""Persistent Windows GDI capture for a small, fixed physical-pixel ROI."""
import ctypes
from ctypes import wintypes

import numpy as np


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD), ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG), ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD), ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD), ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG), ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [('bmiHeader', BITMAPINFOHEADER), ('bmiColors', wintypes.DWORD * 3)]


class Capture:
    """Capture BGRX pixels; the returned array is reused at the next grab."""
    def __init__(self, x, y, width, height):
        if width <= 0 or height <= 0:
            raise ValueError('capture dimensions must be positive')
        self.x, self.y, self.width, self.height = x, y, width, height
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
        self.user32.GetDC.argtypes = [wintypes.HWND]
        self.user32.GetDC.restype = wintypes.HDC
        self.user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self.gdi32.CreateCompatibleDC.restype = wintypes.HDC
        self.gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO),
                                                 wintypes.UINT, ctypes.POINTER(ctypes.c_void_p),
                                                 wintypes.HANDLE, wintypes.DWORD]
        self.gdi32.CreateDIBSection.restype = wintypes.HBITMAP
        self.gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
        self.gdi32.SelectObject.restype = wintypes.HGDIOBJ
        self.gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, wintypes.HDC,
                                      ctypes.c_int, ctypes.c_int, wintypes.DWORD]
        self.gdi32.BitBlt.restype = wintypes.BOOL
        self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self.gdi32.DeleteDC.argtypes = [wintypes.HDC]
        self.src = self.user32.GetDC(None)
        if not self.src:
            raise OSError('GetDC failed')
        self.mem = self.gdi32.CreateCompatibleDC(self.src)
        self.bitmap = None
        self.old = None
        try:
            if not self.mem:
                raise OSError('CreateCompatibleDC failed')
            bmi = BITMAPINFO()
            bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.bmiHeader.biWidth = width
            bmi.bmiHeader.biHeight = -height  # top-down pixel order
            bmi.bmiHeader.biPlanes = 1
            bmi.bmiHeader.biBitCount = 32
            bits = ctypes.c_void_p()
            self.bitmap = self.gdi32.CreateDIBSection(self.src, ctypes.byref(bmi), 0,
                                                       ctypes.byref(bits), None, 0)
            if not self.bitmap or not bits.value:
                raise OSError('CreateDIBSection failed')
            self.old = self.gdi32.SelectObject(self.mem, self.bitmap)
            if not self.old:
                raise OSError('SelectObject failed')
            self.pixels = np.ctypeslib.as_array(
                (ctypes.c_uint8 * (width * height * 4)).from_address(bits.value)
            ).reshape(height, width, 4)
        except Exception:
            self.close()
            raise

    def grab(self):
        if not self.gdi32.BitBlt(self.mem, 0, 0, self.width, self.height,
                                 self.src, self.x, self.y, 0x00CC0020 | 0x40000000):
            raise OSError('BitBlt screen capture failed')
        return self.pixels

    def close(self):
        if self.old:
            self.gdi32.SelectObject(self.mem, self.old)
            self.old = None
        if self.bitmap:
            self.gdi32.DeleteObject(self.bitmap)
            self.bitmap = None
        if self.mem:
            self.gdi32.DeleteDC(self.mem)
            self.mem = None
        if self.src:
            self.user32.ReleaseDC(None, self.src)
            self.src = None

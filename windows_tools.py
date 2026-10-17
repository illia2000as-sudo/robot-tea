"""Safe, small Windows utilities used by Robot Tea."""
import ctypes
import datetime
import os
import platform
import re
import shutil
from pathlib import Path


def _windows_only():
    if os.name != "nt":
        raise OSError("Эта функция доступна только в Windows.")


def system_report():
    """Return basic local system information without collecting or uploading it."""
    _windows_only()
    lines = [
        f"Компьютер: {platform.node() or 'неизвестно'}",
        f"Windows: {platform.system()} {platform.release()} ({platform.machine()})",
        f"Процессор: {platform.processor() or 'неизвестно'}",
    ]
    try:
        usage = shutil.disk_usage(Path.home().anchor or "C:\\")
        lines.append(
            f"Свободно на системном диске: {usage.free // (1024 ** 3)} ГБ "
            f"из {usage.total // (1024 ** 3)} ГБ"
        )
    except OSError:
        pass

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            total = mem.ullTotalPhys // (1024 ** 3)
            free = mem.ullAvailPhys // (1024 ** 3)
            lines.append(f"ОЗУ: свободно {free} ГБ из {total} ГБ (занято {mem.dwMemoryLoad}%)")
    except Exception:
        pass

    class SYSTEM_POWER_STATUS(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
            ("BatteryLifePercent", ctypes.c_ubyte), ("Reserved1", ctypes.c_ubyte),
            ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    try:
        power = SYSTEM_POWER_STATUS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(power)):
            if power.BatteryLifePercent != 255:
                charging = "подключено питание" if power.ACLineStatus == 1 else "питание от батареи"
                lines.append(f"Батарея: {power.BatteryLifePercent}% ({charging})")
    except Exception:
        pass
    return "\n".join(lines)


def find_files(query, limit=8):
    """Search user folders, skipping common bulky/system directories."""
    _windows_only()
    query = (query or "").strip().strip('"').strip("'")
    if len(query) < 2:
        raise ValueError("Укажи хотя бы два символа названия файла.")
    if len(query) > 120:
        raise ValueError("Слишком длинное название.")
    roots = []
    home = Path.home()
    for folder in ("Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music"):
        path = home / folder
        if path.is_dir():
            roots.append(path)
    if not roots:
        roots = [home]

    ignored = {"node_modules", ".git", "__pycache__", "AppData", "Windows", "Program Files"}
    found = []
    needle = query.casefold()
    for root in roots:
        for current, dirs, files in os.walk(root, topdown=True):
            dirs[:] = [d for d in dirs if d not in ignored and not d.startswith(".")]
            for name in files:
                if needle in name.casefold():
                    found.append(str(Path(current) / name))
                    if len(found) >= limit:
                        return found
    return found


def create_folder(name):
    """Create a folder in Documents only; reject paths and unsafe names."""
    _windows_only()
    name = (name or "").strip().strip('"').strip("'")
    if not name or len(name) > 80:
        raise ValueError("Укажи название папки длиной до 80 символов.")
    if name in {".", ".."} or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError("Название папки содержит недопустимые символы.")
    documents = Path.home() / "Documents"
    if not documents.is_dir():
        documents = Path.home() / "Desktop"
    target = documents / name
    target.mkdir(parents=False, exist_ok=False)
    return str(target)


def take_screenshot():
    """Capture the current screen to a local file; nothing is uploaded."""
    _windows_only()
    from PIL import ImageGrab
    pictures = Path.home() / "Pictures"
    if not pictures.is_dir():
        pictures = Path.home() / "Desktop"
    folder = pictures / "RobotTea-Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = folder / f"Screenshot_{stamp}.png"
    image = ImageGrab.grab(all_screens=True)
    image.save(target, "PNG")
    return str(target)

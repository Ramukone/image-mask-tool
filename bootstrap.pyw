"""Windows graphical bootstrap: log uncaught startup and UI callback errors."""
import ctypes
import datetime
from pathlib import Path
import tempfile
import traceback

ROOT = Path(__file__).resolve().parent

def report(details):
    entry = f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n{details}\n"
    target = ROOT / 'startup_error.log'
    try:
        with target.open('a', encoding='utf-8') as log:
            log.write(entry)
    except OSError:
        target = Path(tempfile.gettempdir()) / 'image_mask_startup_error.log'
        try:
            with target.open('a', encoding='utf-8') as log:
                log.write(entry)
        except OSError:
            target = None
    suffix = str(target) if target else '无法写入日志文件'
    ctypes.windll.user32.MessageBoxW(None, '图片蒙版工具遇到错误。\n详细记录：' + suffix, '图片蒙版工具', 0x10)

def main():
    try:
        import app
        app.enable_high_dpi()
        root = app.tk.Tk()
        def callback_error(exc, value, tb):
            report(''.join(traceback.format_exception(exc, value, tb)))
        root.report_callback_exception = callback_error
        app.App(root)
        root.mainloop()
    except Exception:
        report(traceback.format_exc())

if __name__ == '__main__':
    main()

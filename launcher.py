"""Use the selected interpreter; install image libraries only when needed."""
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CHECK = ('import tkinter; from PIL import Image, ImageTk; '
         'assert hasattr(Image, "Resampling"); '
         'from pillow_heif import register_heif_opener; register_heif_opener()')


def environment():
    # Native wheels cannot be shared across interpreter ABIs or architectures.
    tag = '{}-{}-{}'.format(sys.implementation.cache_tag, platform.machine(),
                           getattr(sys, 'abiflags', ''))
    deps = ROOT / '.dependencies' / tag
    env = os.environ.copy()
    env['PYTHONPATH'] = str(deps)
    env.pop('PYTHONHOME', None)
    env['PYTHONUTF8'] = '1'
    return deps, env


def main():
    if sys.version_info < (3, 9):
        raise RuntimeError('需要 Python 3.9 或更新版本。')
    import tkinter
    deps, env = environment()
    result = subprocess.run([sys.executable, '-c', CHECK], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        print('首次运行：正在安装与当前 Python 匹配的图片库……', flush=True)
        pip = subprocess.run([sys.executable, '-m', 'pip', '--version'],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if pip.returncode:
            subprocess.run([sys.executable, '-m', 'ensurepip', '--user'], check=True)
        deps.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--upgrade',
                        '--index-url', 'https://pypi.org/simple',
                        '--only-binary=:all:', '--target', str(deps),
                        'Pillow>=9.1', 'pillow-heif>=0.10'], check=True)
        subprocess.run([sys.executable, '-c', CHECK], env=env, check=True)
    if '--check' in sys.argv:
        print('运行环境检查通过：' + sys.executable)
        return
    # GUI process uses the exact same interpreter, without relying on file associations.
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    executable = str(pythonw) if pythonw.is_file() else sys.executable
    options = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    subprocess.Popen([executable, str(ROOT / 'bootstrap.pyw')], cwd=str(ROOT), env=env, **options)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('启动失败：{}\n请检查网络、pip 和 tkinter 是否可用。'.format(error), file=sys.stderr)
        sys.exit(1)

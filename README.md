# 图片蒙版工具

一个 Windows 桌面图片选区工具。用鼠标绘制多边形，导出选区内部、外部，或同时导出两张透明 PNG。

## 启动

1. 下载仓库 ZIP 并解压。
2. 电脑需已安装 Python 3.9 或更新版本，并包含 tkinter。
3. 双击 `启动.cmd`。首次运行需要联网，程序会检查并安装缺少的图片库。

启动器自动从 PATH、Python Launcher 和 Windows 注册信息中寻找 Python，无需修改用户名或安装路径。明确设置的 `IMAGE_MASK_PYTHON` 优先使用。

Conda 或自定义环境也可以在项目目录运行：

```console
python launcher.py
```

图片库安装到项目内的 `.dependencies`，按解释器和架构分开保存；已有可用依赖时直接使用。删除该文件夹后，下次运行会重新检查并按需下载。程序不附带 Python 运行环境。较新 Python 版本的支持取决于图片库是否提供相应的二进制包。

## 操作

| 操作 | 方法 |
| --- | --- |
| 打开图片 | “打开图片”或 Ctrl+O |
| 添加节点 | 单击图片 |
| 闭合选区 | 点击起点或按 Enter |
| 平移图片 | 按住左键拖动 |
| 缩放 | 鼠标滚轮 |
| 撤销 | Backspace 或 Ctrl+Z |
| 清空选区 | Esc 或“重新绘制” |
| 导出 | “导出内部”“导出外部”或“同时导出” |

至少需要三个不共线节点，边线不能相交。闭合后撤销会重新打开选区。

输出保留图片转正后的原始尺寸与透明度，边缘抗锯齿。重名文件自动编号，不覆盖已有文件；同时导出中途失败时，会尝试清理本次输出。

支持 PNG、JPEG、WebP、BMP、TIFF、HEIC、HEIF。AVIF 支持取决于所安装 Pillow 的编解码能力。HEIF 多图文件读取主图，其他多帧图片读取首帧。16 位无符号灰度图映射为 8 位灰度后导出 RGBA PNG。

## 检查与测试

检查运行环境（缺少依赖时会安装）：

```console
python launcher.py --check
```

在 Windows 桌面会话中验证启动入口、两种控制台编码及 Python 查找容错：

```console
python test_launch.py
```

功能测试需当前环境能够导入 Pillow 和 pillow-heif。如果依赖安装在 `.dependencies` 中，可使用以下命令加载同一环境并运行测试：

```console
python -c "import launcher, subprocess, sys; _, env = launcher.environment(); subprocess.run([sys.executable, 'test_app.py'], env=env, check=True); subprocess.run([sys.executable, '-m', 'unittest', 'test_regressions.py'], env=env, check=True)"
```

启动和界面异常记录在 `startup_error.log`；项目目录不可写时使用系统临时目录。

"""
Build Script - Package application into exe
Usage: python build.py

Features:
- Auto-install missing dependencies
- Auto-detect and handle DLL issues
- Auto-compile Go downloader (if Go installed)
- Compatible with various Python environments
"""
import os
import sys
import shutil
import subprocess
import re
import io
from datetime import datetime
from pathlib import Path

# Fix encoding for Windows CI (cp1252 -> utf-8)
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 项目版本信息
VERSION = "2.4.0"
BUILD_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
AUTHOR = "zfonlyone"
COPYRIGHT = f"Copyright © {datetime.now().year} zfonlyone. All rights reserved."

# Required packages
REQUIRED_PACKAGES = [
    "pyinstaller",
    "PyQt5",
    "aiohttp",
    "aiofiles",
    "requests",
]


def install_package(package: str) -> bool:
    """安装单个包"""
    try:
        print(f"  正在安装 {package}...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", package, "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"  ✗ 安装 {package} 失败: {e}")
        return False


def ensure_dependencies():
    """确保所有依赖已安装"""
    print("\n=== 检查依赖 ===")
    
    missing = []
    for package in REQUIRED_PACKAGES:
        try:
            __import__(package.lower().replace("-", "_"))
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"发现 {len(missing)} 个缺失的依赖，正在安装...")
        for package in missing:
            install_package(package)
    else:
        print("✓ 所有依赖已就绪")
    
    # 检查并移除有问题的 pathlib
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "pathlib"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("发现多余的 pathlib 包，正在移除...")
            subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "pathlib"],
                          capture_output=True)
    except:
        pass


def find_dll_files():
    """查找需要的 DLL 文件"""
    print("\n=== 查找 DLL 文件 ===")
    
    python_dir = Path(sys.executable).parent
    dll_search_paths = [
        python_dir / "DLLs",
        python_dir / "Library" / "bin",  # Anaconda
        python_dir,
    ]
    
    needed_dlls = ["sqlite3.dll", "libssl-*.dll", "libcrypto-*.dll"]
    found_dlls = []
    
    for dll_pattern in needed_dlls:
        for search_path in dll_search_paths:
            if not search_path.exists():
                continue
            
            import glob
            matches = glob.glob(str(search_path / dll_pattern))
            for match in matches:
                if match not in found_dlls:
                    found_dlls.append(match)
                    print(f"  找到: {match}")
    
    return found_dlls


def build_go_downloader():
    """编译 Go 下载器"""
    print("\n=== 编译 Go 下载器 ===")
    
    go_source_dir = Path("tools/downloader")
    go_source_file = go_source_dir / "main.go"
    go_output = Path("downloader.exe")
    
    if not go_source_file.exists():
        print(f"⚠ Go 源文件不存在: {go_source_file}")
        return None
    
    # 检查 Go 是否可用
    try:
        result = subprocess.run(["go", "version"], capture_output=True, text=True)
        if result.returncode != 0:
            print("⚠ Go 不可用，跳过编译")
            return None
        print(f"Go 版本: {result.stdout.strip()}")
    except FileNotFoundError:
        print("⚠ 未安装 Go，跳过编译")
        print("  提示: 安装 Go (https://go.dev/dl/) 后可获得最佳下载性能")
        return None
    
    # 编译
    print(f"正在编译 {go_source_file}...")
    try:
        result = subprocess.run(
            ["go", "build", "-ldflags", "-s -w", "-o", "../../downloader.exe", "main.go"],
            cwd=str(go_source_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print(f"✓ Go 下载器编译成功: {go_output}")
            return go_output
        else:
            print(f"✗ Go 编译失败: {result.stderr}")
            return None
    except Exception as e:
        print(f"✗ Go 编译出错: {e}")
        return None


def update_project_info():
    """更新项目信息"""
    print("\n=== 更新项目信息 ===")
    
    project_info_path = Path("models/project_info.py")
    if not project_info_path.exists():
        print(f"⚠ 找不到项目信息文件: {project_info_path}")
        return
    
    content = project_info_path.read_text(encoding="utf-8")
    
    replacements = [
        (r'("version"\s*:\s*)"[\d\.]+"', f'\\1"{VERSION}"'),
        (r'("build_date"\s*:\s*)"[^"]*"', f'\\1"{BUILD_DATE}"'),
        (r'("author"\s*:\s*)"[^"]*"', f'\\1"{AUTHOR}"'),
        (r'("copyright"\s*:\s*f*)"[^"]*"', f'\\1"{COPYRIGHT}"'),
    ]
    
    for pattern, replacement in replacements:
        content = re.sub(pattern, replacement, content)
    
    project_info_path.write_text(content, encoding="utf-8")
    print(f"✓ 版本={VERSION}, 构建日期={BUILD_DATE}")


def cleanup():
    """清理之前的构建文件"""
    print("\n=== 清理旧文件 ===")
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"  删除 {folder}/")
    
    for spec in Path(".").glob("*.spec"):
        spec.unlink()
        print(f"  删除 {spec}")


def build_exe(dlls):
    """构建EXE文件"""
    print("\n=== 构建主程序 ===")
    
    # 创建版本信息文件
    version_info = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION.replace(".", ", ")}, 0),
    prodvers=({VERSION.replace(".", ", ")}, 0),
    mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(u'040904B0', [
        StringStruct(u'CompanyName', u'{AUTHOR}'),
        StringStruct(u'FileDescription', u'Steam Game Unlocker'),
        StringStruct(u'FileVersion', u'{VERSION}'),
        StringStruct(u'ProductName', u'Steam Game Unlocker'),
        StringStruct(u'ProductVersion', u'{VERSION}'),
        StringStruct(u'LegalCopyright', u'{COPYRIGHT}'),
      ])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    version_file = Path("version_info.txt")
    version_file.write_text(version_info, encoding="utf-8")
    
    # 处理图标
    icon_arg = ""
    icon_png = Path("app_icon.png")
    icon_ico = Path("app_icon.ico")
    
    if icon_png.exists():
        # 尝试将 PNG 转换为 ICO
        if not icon_ico.exists():
            try:
                from PIL import Image
                img = Image.open(icon_png)
                img.save(icon_ico, format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
                print(f"✓ 已将 {icon_png} 转换为 {icon_ico}")
            except ImportError:
                print("⚠ 未安装 Pillow，使用 pip install Pillow 可启用图标转换")
            except Exception as e:
                print(f"⚠ 图标转换失败: {e}")
        
        if icon_ico.exists():
            icon_arg = f"--icon={icon_ico}"
            print(f"✓ 使用图标: {icon_ico}")
    
    # 构建参数
    cmd = [
        sys.executable, "-m", "PyInstaller",
        f"--name=SteamGameUnlocker-{VERSION}",
        "--windowed",
        "--onefile",
        "--clean",
        "--noconfirm",
        f"--version-file={version_file}",
        # 隐藏导入
        "--hidden-import=sqlite3",
        "--hidden-import=aiohttp",
        "--hidden-import=aiofiles",
        "--hidden-import=asyncio",
    ]
    
    if icon_arg:
        cmd.append(icon_arg)
    
    # 添加 DLL 文件
    for dll in dlls:
        cmd.extend(["--add-binary", f"{dll}{os.pathsep}."])
    
    # 添加数据文件
    data_files = [
        ("config.json", "."),
        ("games_data.json", "."),
        ("README.md", "."),
        ("app_icon.png", "."),  # 图标也作为数据文件包含
        # 工具脚本 - 必须包含所有工具
        ("tools/downloader.py", "tools"),
        ("tools/check_addappid.py", "tools"),
        ("tools/replace_manifest.py", "tools"),
        ("tools/enable_manifest.py", "tools"),
        ("tools/find_no_manifest.py", "tools"),
        ("tools/clean_invalid_lua.py", "tools"),
        ("tools/recover_manifests_from_lua.py", "tools"),
        ("tools/fix_lua_formats.py", "tools"),
        ("tools/fetch_dlc.py", "tools"),
        ("tools/complete_manifests.py", "tools"),
    ]

    for src, dst in data_files:

        if os.path.exists(src):
            cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])
    
    cmd.append("app.py")
    
    print(f"执行 PyInstaller...")
    try:
        subprocess.check_call(cmd)
    finally:
        if version_file.exists():
            version_file.unlink()
    
    print(f"\n✓ 主程序构建完成: dist/SteamGameUnlocker-{VERSION}.exe")


def copy_go_downloader():
    """复制 Go 下载器到 dist 文件夹"""
    go_binary = Path("downloader.exe")
    dist_dir = Path("dist")
    
    if go_binary.exists():
        dest = dist_dir / "downloader.exe"
        shutil.copy2(str(go_binary), str(dest))
        print(f"✓ 已复制 Go 下载器到: {dest}")
        return True
    return False


def main():
    """主函数"""
    print(f"{'='*50}")
    print(f"  Steam游戏解锁器打包工具 v{VERSION}")
    print(f"{'='*50}")
    
    # 1. 安装依赖
    ensure_dependencies()
    
    # 2. 更新项目信息
    update_project_info()
    
    # 3. 清理旧文件
    cleanup()
    
    # 4. 查找 DLL
    dlls = find_dll_files()
    
    # 5. 编译 Go 下载器
    go_binary = build_go_downloader()
    
    # 6. 构建主程序
    build_exe(dlls)
    
    # 7. 复制 Go 下载器
    has_go = False
    if go_binary:
        has_go = copy_go_downloader()
    
    # 8. 完成
    print(f"\n{'='*50}")
    print(f"  ✓ 打包完成!")
    print(f"{'='*50}")
    print(f"\n输出文件夹: dist/")
    print(f"  - SteamGameUnlocker-{VERSION}.exe (主程序)")
    if has_go:
        print(f"  - downloader.exe (Go 高速下载器)")


if __name__ == "__main__":
    main()
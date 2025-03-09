"""
打包脚本 - 将应用程序打包为exe文件
使用方法: python build.py
"""
import os
import sys
import shutil
import subprocess

def ensure_pyinstaller():
    """确保已安装PyInstaller"""
    try:
        import PyInstaller
        print("PyInstaller已安装，版本:", PyInstaller.__version__)
    except ImportError:
        print("正在安装PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装完成")

def cleanup():
    """清理之前的构建文件"""
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            print(f"删除旧的{folder}文件夹...")
            shutil.rmtree(folder)
    
    spec_file = "app.spec"
    if os.path.exists(spec_file):
        print(f"删除旧的{spec_file}文件...")
        os.remove(spec_file)

def check_and_remove_pathlib():
    """检查并移除pathlib包（在Python 3.4+中已内置）"""
    try:
        # 尝试卸载pathlib
        print("检查是否安装了多余的pathlib包...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "pathlib"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("发现多余的pathlib包，正在卸载...")
            subprocess.check_call([sys.executable, "-m", "pip", "uninstall", "-y", "pathlib"])
            print("pathlib包卸载完成")
        else:
            print("未发现多余的pathlib包，继续...")
    except Exception as e:
        print(f"警告: 尝试卸载pathlib时出错: {e}")
        print("请手动运行以下命令卸载pathlib包:")
        print(f"{sys.executable} -m pip uninstall pathlib")

def build_exe():
    """构建EXE文件"""
    print("正在构建应用程序...")
    
    # 要包含的数据文件
    data_files = [
        ('config.json', '.'),
        ('games_data.json', '.'),
        ('README.md', '.')
    ]
    
    data_args = []
    for src, dst in data_files:
        if os.path.exists(src):
            data_args.extend(['--add-data', f'{src}{os.pathsep}{dst}'])
    
    # 构建命令
    cmd = [
        "pyinstaller",
        "--name=SteamGameUnlocker",
        "--windowed",  # 使用GUI模式，不显示控制台
        "--onefile",   # 打包成单个exe文件
        "--icon=NONE", # 可以替换为实际的图标文件
        "--clean",     # 清理临时文件
        "--noconfirm", # 不询问确认
    ] + data_args + ["app1.py"]
    
    print("执行命令:", " ".join(cmd))
    subprocess.check_call(cmd)
    
    print("\n构建完成！可执行文件位于 dist 文件夹中")
    print("您可以运行 dist/SteamGameUnlocker.exe 来启动程序")

def main():
    """主函数"""
    print("=== Steam游戏解锁器打包工具 ===")
    ensure_pyinstaller()
    check_and_remove_pathlib()  # 添加检查和卸载pathlib的步骤
    cleanup()
    build_exe()
    
    # 创建启动脚本
    with open("dist/启动程序.bat", "w", encoding="utf-8") as f:
        f.write("@echo off\nstart SteamGameUnlocker.exe\n")

if __name__ == "__main__":
    main() 
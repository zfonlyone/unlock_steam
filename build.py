"""
打包脚本 - 将应用程序打包为exe文件
使用方法: python build.py
"""
import os
import sys
import shutil
import subprocess
import json
import time
import re
from datetime import datetime

# 项目版本信息
VERSION = "1.2.0"  # 当前版本号
BUILD_DATE = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
AUTHOR = "zfonlyone"
COPYRIGHT = f"Copyright © {datetime.now().year} Your Name. All rights reserved."

def ensure_pyinstaller():
    """确保已安装PyInstaller"""
    try:
        import PyInstaller
        print("PyInstaller已安装，版本:", PyInstaller.__version__)
    except ImportError:
        print("正在安装PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装完成")

def update_project_info():
    """更新项目信息"""
    print("正在更新项目信息...")
    
    # 项目信息文件路径
    project_info_path = os.path.join("models", "project_info.py")
    
    if not os.path.exists(project_info_path):
        print(f"警告: 找不到项目信息文件: {project_info_path}")
        return
    
    # 读取项目信息文件
    with open(project_info_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 更新版本号
    content = re.sub(
        r'("version"\s*:\s*)"[\d\.]+"', 
        f'\\1"{VERSION}"', 
        content
    )
    
    # 更新构建日期
    content = re.sub(
        r'("build_date"\s*:\s*)"[^"]*"', 
        f'\\1"{BUILD_DATE}"', 
        content
    )
    
    # 更新作者
    content = re.sub(
        r'("author"\s*:\s*)"[^"]*"', 
        f'\\1"{AUTHOR}"', 
        content
    )
    
    # 更新版权信息
    content = re.sub(
        r'("copyright"\s*:\s*f*)"[^"]*"', 
        f'\\1"{COPYRIGHT}"', 
        content
    )
    
    # 写回项目信息文件
    with open(project_info_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print(f"项目信息已更新: 版本={VERSION}, 构建日期={BUILD_DATE}")

def cleanup():
    """清理之前的构建文件"""
    for folder in ['build', 'dist']:
        if os.path.exists(folder):
            print(f"删除旧的{folder}文件夹...")
            shutil.rmtree(folder)
    
    spec_file = "SteamGameUnlocker.spec"
    if os.path.exists(spec_file):
        print(f"删除旧的{spec_file}文件...")
        os.remove(spec_file)


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
    
    # 创建版本信息文件
    version_info = f"""
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({VERSION.replace(".", ", ")}, 0),
    prodvers=({VERSION.replace(".", ", ")}, 0),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u'040904B0',
          [StringStruct(u'CompanyName', u'{AUTHOR}'),
           StringStruct(u'FileDescription', u'Steam Game Unlocker'),
           StringStruct(u'FileVersion', u'{VERSION}'),
           StringStruct(u'InternalName', u'SteamGameUnlocker'),
           StringStruct(u'LegalCopyright', u'{COPYRIGHT}'),
           StringStruct(u'OriginalFilename', u'SteamGameUnlocker.exe'),
           StringStruct(u'ProductName', u'Steam Game Unlocker'),
           StringStruct(u'ProductVersion', u'{VERSION}')])
      ]
    ),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    version_file = "version_info.txt"
    with open(version_file, "w", encoding="utf-8") as f:
        f.write(version_info)
    
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
        f"--name=SteamGameUnlocker-{VERSION}",
        "--windowed",  # 使用GUI模式，不显示控制台
        "--onefile",   # 打包成单个exe文件
        "--icon=NONE", # 可以替换为实际的图标文件
        "--clean",     # 清理临时文件
        "--noconfirm", # 不询问确认
        f"--version-file={version_file}",  # 版本信息文件
    ] + data_args + ["app.py"]
    
    print("执行命令:", " ".join(cmd))
    subprocess.check_call(cmd)
    
    # 删除版本信息文件
    if os.path.exists(version_file):
        os.remove(version_file)
    
    print("\n构建完成！可执行文件位于 dist 文件夹中")
    print(f"您可以运行 dist/SteamGameUnlocker-{VERSION}.exe 来启动程序")

def main():
    """主函数"""
    print(f"=== Steam游戏解锁器打包工具 v{VERSION} ===")
    ensure_pyinstaller()
    update_project_info()  # 更新项目信息
    cleanup()
    build_exe()
    
    # 创建启动脚本
    with open(f"dist/启动程序-v{VERSION}.bat", "w", encoding="utf-8") as f:
        f.write(f"@echo off\nstart SteamGameUnlocker-{VERSION}.exe\n")

if __name__ == "__main__":
    main() 
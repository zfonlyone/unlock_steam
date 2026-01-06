import os
import re
import json
import subprocess
import pathlib
import sys
import tempfile
from typing import Dict, List

def run_recovery(lua_dir: str, output_manifest_dir: str, downloader_path: str, repo: str, token: str = ""):
    """
    补全工具 V15 版：
    1. 使用 Lua 文件名作为 AppID/分支名。
    2. 使用临时文件传递 JSON 配置，解决 Stdin 管道容量限制引起的卡死。
    3. 支持多种清单命名匹配尝试。
    """
    lua_path = pathlib.Path(lua_dir)
    if not lua_path.exists():
        print(f"错误: 目录 {lua_dir} 不存在")
        return

    app_data = {}
    app_ids = []
    
    # 正则：setManifestid(depot_id, "manifestid") 或 setManifestid(depot_id, manifestid)
    manifest_pattern = re.compile(r'setManifestid\s*\(\s*(\d+)\s*,\s*["\']?(\d+)["\']?\s*\)')
    
    print(f"正在扫描 {lua_dir} 中的 Lua 文件...")
    lua_files = list(lua_path.glob("*.lua"))
    total_files = len(lua_files)
    
    for i, f in enumerate(lua_files):
        if i % 1000 == 0:
            print(f"已处理 {i}/{total_files} 个文件...")
            
        main_appid = f.stem # 比如 2087470.lua -> 2087470 (对应分支)
        try:
            content = f.read_text(encoding='utf-8', errors='ignore')
            matches = manifest_pattern.findall(content)
            for depot_id, mid in matches:
                if main_appid not in app_data:
                    app_data[main_appid] = []
                    app_ids.append(main_appid)
                
                # 存入 DepotID_ManifestID，Go v15 会尝试这个及其他变体
                full_item = f"{depot_id}_{mid}"
                if full_item not in app_data[main_appid]:
                    app_data[main_appid].append(full_item)
        except Exception as e:
            print(f"解析 {f.name} 失败: {e}")

    if not app_data:
        print("未在 Lua 目录中提取到有效 setManifestid 数据")
        return

    print(f"扫描完毕！发现 {len(app_ids)} 个相关的 AppID 分支。")
    
    # 核心：将配置写入临时文件，避免 Stdin 卡死
    config = {
        "token": token,
        "repo": repo,
        "app_ids": app_ids,
        "app_data": app_data,
        "lua_dir": "", 
        "manifest_dir": output_manifest_dir,
        "direct_mode": True,
        "manifest_only": True
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
        json.dump(config, tmp)
        temp_config_path = tmp.name

    print(f"正在启动 V15 下载器 (配置已载入)...")
    try:
        # 使用 -config 标志调用
        process = subprocess.Popen(
            [downloader_path, "-config", temp_config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1
        )
        
        # 实时解析进度输出
        while True:
            line = process.stdout.readline()
            if not line and process.poll() is not None:
                break
            if line:
                line = line.strip()
                if "[PROGRESS]" in line:
                    p = line.split("]")[-1].strip()
                    print(f"\r🚀 下载进度: {p}", end="", flush=True)
                elif "[DOWNLOAD_SUCCESS]" in line:
                    # 如果需要调试，可以取消下面注释
                    # print(f"\n✅ {line}")
                    pass
                elif "[DOWNLOAD_FAIL]" in line:
                    # 如果 404 太频繁可以略过，或者只打印重要的
                    # print(f"\n❌ {line}")
                    pass
                elif not line.startswith("{"):
                    print(f"\n{line}")

        process.wait()
        print(f"\n任务圆满结束。")
            
    finally:
        # 清理临时文件
        if os.path.exists(temp_config_path):
            os.remove(temp_config_path)

if __name__ == "__main__":
    # 配置
    LUA_SOURCE = r"C:\Game\s"
    MANIFEST_DEST = r"C:\Program Files (x86)\Steam\config\depotcache"
    REPO = "SteamAutoCracks/ManifestHub"
    
    # 获取项目路径
    PROJECT_ROOT = pathlib.Path(__file__).parent.parent
    DOWNLOADER = str(PROJECT_ROOT / "downloader.exe")
    TOKEN = ""

    # 尝试从主配置加载仓库
    try:
        with open(PROJECT_ROOT / "config.json", "r", encoding='utf-8') as f:
            cfg = json.load(f)
            r_url = cfg.get("repositories", [{}])[0].get("url", "")
            if "github.com/" in r_url:
                REPO = r_url.split("github.com/")[-1].replace(".git", "").strip("/")
            TOKEN = cfg.get("github_token", "")
    except:
        pass

    print(f"--- 清单恢复工具 (V15 管道优化版) ---")
    print(f"扫码目录: {LUA_SOURCE}")
    print(f"下载目标: {MANIFEST_DEST}")
    print(f"使用仓库: {REPO}")
    
    run_recovery(LUA_SOURCE, MANIFEST_DEST, DOWNLOADER, REPO, TOKEN)

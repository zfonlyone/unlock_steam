"""
清单补全工具

功能：
1. 解析 Lua 文件获取所有 addappid 条目的 depot ID
2. 从 GitHub 分支获取所有 manifest 文件列表
3. 下载缺失的 manifest 到 depotcache 目录

直接调用:
    from tools.complete_manifests import run_complete_single, run_complete_all
    result = run_complete_single(app_id, lua_dir, depot_cache, progress_callback)
    result = run_complete_all(lua_dir, depot_cache, progress_callback)
"""
import os
import re
import time
import json
import urllib.request
import urllib.error
from typing import List, Set, Dict, Tuple, Any, Optional, Callable
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# GitHub 仓库配置
REPO_PATH = "SteamAutoCracks/ManifestHub"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{REPO_PATH}"
API_BASE_URL = f"https://api.github.com/repos/{REPO_PATH}"


def get_depot_ids_from_lua(lua_path: str) -> Set[str]:
    """
    从 Lua 文件提取所有 addappid 的 depot ID
    
    Args:
        lua_path: Lua 文件路径
        
    Returns:
        depot ID 集合
    """
    depot_ids = set()
    pattern = re.compile(r'addappid\s*\(\s*(\d+)', re.IGNORECASE)
    
    try:
        content = Path(lua_path).read_text(encoding='utf-8', errors='ignore')
        matches = pattern.findall(content)
        depot_ids = set(matches)
    except Exception as e:
        print(f"读取 Lua 文件失败: {e}")
    
    return depot_ids


def get_existing_manifest_files(depot_cache: str) -> Set[str]:
    """
    获取 depotcache 中已存在的 manifest 文件名
    
    Args:
        depot_cache: depotcache 目录路径
        
    Returns:
        已存在的 manifest 文件名集合 (完整文件名)
    """
    existing = set()
    depot_cache_path = Path(depot_cache)
    
    if not depot_cache_path.exists():
        return existing
    
    # 返回完整文件名，确保不同版本的 manifest 都能被检测
    for f in depot_cache_path.glob("*.manifest"):
        existing.add(f.name)
    
    return existing


def get_manifests_from_github(app_id: str, retry: int = 3) -> List[Tuple[str, str]]:
    """
    从 GitHub 分支获取所有 manifest 文件列表
    
    Args:
        app_id: 游戏 App ID (也是分支名)
        retry: 重试次数
        
    Returns:
        [(depot_id, download_url), ...] 列表
    """
    manifests = []
    api_url = f"{API_BASE_URL}/contents?ref={app_id}"
    headers = {"User-Agent": "SteamUnlocker/2.3", "Accept": "application/vnd.github.v3+json"}
    
    for attempt in range(retry):
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                files_info = json.loads(response.read().decode('utf-8'))
                
                for file_info in files_info:
                    if not isinstance(file_info, dict):
                        continue
                    
                    filename = file_info.get("name", "")
                    if filename.endswith(".manifest"):
                        # 提取 depot_id (格式: {depot_id}_{gid}.manifest)
                        parts = filename[:-9].split("_")  # 去掉 .manifest
                        if parts and parts[0].isdigit():
                            depot_id = parts[0]
                            download_url = file_info.get("download_url") or f"{RAW_BASE_URL}/{app_id}/{filename}"
                            manifests.append((depot_id, download_url, filename))
                
                return manifests
                
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []  # 分支不存在
            elif e.code == 403:
                # API 限速
                if attempt < retry - 1:
                    time.sleep(2)
                continue
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
            continue
    
    return manifests


def download_manifest(url: str, dest_path: str, filename: str) -> Tuple[bool, str, int]:
    """下载单个 manifest 文件"""
    try:
        headers = {"User-Agent": "SteamUnlocker/2.3"}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as response:
            content = response.read()
            with open(dest_path, 'wb') as f:
                f.write(content)
            return (True, filename, len(content))
    except Exception as e:
        return (False, filename, str(e))


def run_complete_single(
    app_id: str,
    lua_dir: str,
    depot_cache: str,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    补全单个游戏的清单
    
    Args:
        app_id: 游戏 App ID
        lua_dir: Lua 文件所在目录 (stplug-in)
        depot_cache: depotcache 目录路径
        progress_callback: 进度回调函数
        
    Returns:
        {"success": bool, "downloaded": int, "skipped": int, "message": str}
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    lua_path = os.path.join(lua_dir, f"{app_id}.lua")
    
    if not os.path.exists(lua_path):
        return {"success": False, "downloaded": 0, "skipped": 0,
                "message": f"Lua 文件不存在: {app_id}.lua"}
    
    log(f"正在解析 {app_id}.lua 获取 depot 列表...")
    
    # 获取 Lua 中的所有 depot ID
    depot_ids = get_depot_ids_from_lua(lua_path)
    if not depot_ids:
        return {"success": True, "downloaded": 0, "skipped": 0,
                "message": f"Lua 文件中没有 addappid 条目"}
    
    log(f"找到 {len(depot_ids)} 个 depot，正在获取 GitHub 清单列表...")
    
    # 获取 GitHub 上的 manifest 文件
    github_manifests = get_manifests_from_github(app_id)
    
    if not github_manifests:
        return {"success": True, "downloaded": 0, "skipped": 0,
                "message": f"GitHub 分支 {app_id} 没有 manifest 文件或不存在"}
    
    log(f"GitHub 分支有 {len(github_manifests)} 个 manifest 文件")
    
    # 获取本地已有的 manifest 文件名
    existing_files = get_existing_manifest_files(depot_cache)
    
    # 筛选需要下载的 manifest:
    # 1. depot ID 在 Lua 中存在
    # 2. 该 manifest 文件本地不存在 (通过完整文件名判断)
    to_download = []
    for depot_id, url, filename in github_manifests:
        if depot_id in depot_ids and filename not in existing_files:
            to_download.append((url, os.path.join(depot_cache, filename), filename))
    
    skipped = len(github_manifests) - len(to_download)
    
    if not to_download:
        return {"success": True, "downloaded": 0, "skipped": skipped,
                "message": f"所有 manifest 已存在，无需下载"}
    
    log(f"需要下载 {len(to_download)} 个 manifest...")
    
    # 确保目录存在
    os.makedirs(depot_cache, exist_ok=True)
    
    # 并发下载
    downloaded = 0
    max_workers = min(10, len(to_download))
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download_manifest, url, dest, name) 
                   for url, dest, name in to_download]
        
        for future in as_completed(futures):
            success, filename, info = future.result()
            if success:
                downloaded += 1
                log(f"已下载: {filename}")
            else:
                log(f"下载失败: {filename} - {info}")
    
    return {
        "success": True,
        "downloaded": downloaded,
        "skipped": skipped,
        "message": f"下载完成！新增 {downloaded} 个 manifest，跳过 {skipped} 个已存在的"
    }


def run_complete_all(
    lua_dir: str,
    depot_cache: str,
    progress_callback: Optional[Callable] = None
) -> Dict[str, Any]:
    """
    批量补全所有游戏的清单
    
    Args:
        lua_dir: Lua 文件所在目录 (stplug-in)
        depot_cache: depotcache 目录路径
        progress_callback: 进度回调函数
        
    Returns:
        {"success": bool, "total_games": int, "total_downloaded": int, "message": str}
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg)
    
    lua_path = Path(lua_dir)
    if not lua_path.exists():
        return {"success": False, "total_games": 0, "total_downloaded": 0,
                "message": f"目录不存在: {lua_dir}"}
    
    # 获取所有数字命名的 Lua 文件
    lua_files = [f for f in lua_path.glob("*.lua") if f.stem.isdigit()]
    
    if not lua_files:
        return {"success": True, "total_games": 0, "total_downloaded": 0,
                "message": "未找到任何已解锁的游戏"}
    
    log(f"找到 {len(lua_files)} 个已解锁的游戏，开始补全清单...")
    
    total_downloaded = 0
    processed = 0
    errors = []
    
    for i, lua_file in enumerate(lua_files):
        app_id = lua_file.stem
        
        try:
            log(f"[{i+1}/{len(lua_files)}] 正在处理 {app_id}...")
            
            result = run_complete_single(app_id, lua_dir, depot_cache)
            
            if result["downloaded"] > 0:
                total_downloaded += result["downloaded"]
                log(f"  → 下载 {result['downloaded']} 个 manifest")
            
            processed += 1
            
            # 避免 API 限速
            if i < len(lua_files) - 1:
                time.sleep(0.5)
                
        except Exception as e:
            errors.append(f"{app_id}: {e}")
            continue
    
    message = f"处理完成！共 {processed} 个游戏，下载 {total_downloaded} 个 manifest"
    if errors:
        message += f"，{len(errors)} 个错误"
    
    log(message)
    
    return {
        "success": True,
        "total_games": processed,
        "total_downloaded": total_downloaded,
        "errors": errors,
        "message": message
    }


def main():
    """命令行入口"""
    import sys
    
    if len(sys.argv) < 3:
        print("用法: python complete_manifests.py <app_id|--all> <lua_dir> [depot_cache]")
        return
    
    mode = sys.argv[1]
    lua_dir = sys.argv[2]
    depot_cache = sys.argv[3] if len(sys.argv) > 3 else os.path.join(
        os.path.dirname(lua_dir), "depotcache"
    )
    
    def print_progress(msg):
        print(f"  {msg}")
    
    if mode == "--all":
        result = run_complete_all(lua_dir, depot_cache, print_progress)
    else:
        result = run_complete_single(mode, lua_dir, depot_cache, print_progress)
    
    print(f"\n{result['message']}")


if __name__ == '__main__':
    main()

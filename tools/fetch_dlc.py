"""
DLC 获取并添加工具

功能：
1. 从 Steam API 获取游戏的所有 DLC App ID
2. 将 DLC App ID 添加到对应的 Lua 文件中
3. 自动去重：跳过已存在的 App ID
4. 添加格式：addappid(id)

直接调用:
    from tools.fetch_dlc import run_fetch_single, run_fetch_all
    result = run_fetch_single(app_id, lua_dir, progress_callback)
    result = run_fetch_all(lua_dir, progress_callback)

命令行:
    python fetch_dlc.py <app_id> [lua_dir]
    python fetch_dlc.py --all [lua_dir]
"""
import os
import re
import time
import requests
from typing import List, Set, Dict, Any, Optional, Callable
import pathlib


def get_dlc_list(app_id: str, retry: int = 3) -> List[str]:
    """
    从 Steam API 获取游戏的所有 DLC App ID
    
    Args:
        app_id: 游戏的 App ID
        retry: 重试次数
        
    Returns:
        DLC App ID 列表
    """
    url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
    
    for attempt in range(retry):
        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if data.get(str(app_id), {}).get("success"):
                    dlc_list = data[str(app_id)].get("data", {}).get("dlc", [])
                    return [str(d) for d in dlc_list]
            # 请求限制，等待后重试
            if attempt < retry - 1:
                time.sleep(1)
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
            continue
    
    return []


def get_existing_appids(lua_path: str) -> Set[str]:
    """
    从 Lua 文件中提取已存在的 App ID
    
    Args:
        lua_path: Lua 文件路径
        
    Returns:
        已存在的 App ID 集合
    """
    existing = set()
    pattern = re.compile(r'addappid\s*\(\s*(\d+)', re.IGNORECASE)
    
    try:
        content = pathlib.Path(lua_path).read_text(encoding='utf-8', errors='ignore')
        matches = pattern.findall(content)
        existing = set(matches)
    except Exception:
        pass
    
    return existing


def add_dlc_to_lua(lua_path: str, dlc_ids: List[str], progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    向 Lua 文件添加 DLC 条目（自动去重）
    
    Args:
        lua_path: Lua 文件路径
        dlc_ids: 要添加的 DLC App ID 列表
        progress_callback: 进度回调函数
        
    Returns:
        {"success": bool, "added": int, "skipped": int, "message": str}
    """
    if not os.path.exists(lua_path):
        return {"success": False, "added": 0, "skipped": 0, "message": f"文件不存在: {lua_path}"}
    
    # 获取已存在的 App ID
    existing = get_existing_appids(lua_path)
    
    # 过滤需要添加的 DLC
    to_add = [d for d in dlc_ids if d not in existing]
    skipped = len(dlc_ids) - len(to_add)
    
    if not to_add:
        return {"success": True, "added": 0, "skipped": skipped, "message": "无新 DLC 需要添加"}
    
    try:
        # 读取现有内容
        content = pathlib.Path(lua_path).read_text(encoding='utf-8', errors='ignore')
        
        # 生成新的 DLC 条目
        new_lines = [f"addappid({dlc_id})" for dlc_id in to_add]
        
        # 追加到文件末尾
        if content and not content.endswith('\n'):
            content += '\n'
        content += '\n'.join(new_lines) + '\n'
        
        # 写入文件
        pathlib.Path(lua_path).write_text(content, encoding='utf-8')
        
        if progress_callback:
            progress_callback(f"已添加 {len(to_add)} 个 DLC 到 {os.path.basename(lua_path)}")
        
        return {"success": True, "added": len(to_add), "skipped": skipped, 
                "message": f"成功添加 {len(to_add)} 个 DLC，跳过 {skipped} 个已存在的"}
    except Exception as e:
        return {"success": False, "added": 0, "skipped": 0, "message": f"写入失败: {e}"}


def run_fetch_single(app_id: str, lua_dir: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    获取单个游戏的 DLC 并添加到 Lua 文件
    
    Args:
        app_id: 游戏 App ID
        lua_dir: Lua 文件所在目录 (stplug-in 目录)
        progress_callback: 进度回调函数
        
    Returns:
        {"success": bool, "dlc_count": int, "added": int, "message": str}
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
    
    lua_path = os.path.join(lua_dir, f"{app_id}.lua")
    
    if not os.path.exists(lua_path):
        return {"success": False, "dlc_count": 0, "added": 0, 
                "message": f"Lua 文件不存在: {app_id}.lua，请先解锁游戏"}
    
    log(f"正在获取 {app_id} 的 DLC 列表...")
    
    # 获取 DLC 列表
    dlc_list = get_dlc_list(app_id)
    
    if not dlc_list:
        return {"success": True, "dlc_count": 0, "added": 0, 
                "message": f"游戏 {app_id} 没有 DLC 或获取失败"}
    
    log(f"获取到 {len(dlc_list)} 个 DLC，正在添加...")
    
    # 添加 DLC 到 Lua 文件
    result = add_dlc_to_lua(lua_path, dlc_list, progress_callback)
    
    return {
        "success": result["success"],
        "dlc_count": len(dlc_list),
        "added": result["added"],
        "skipped": result["skipped"],
        "message": f"获取到 {len(dlc_list)} 个 DLC，{result['message']}"
    }


def run_fetch_all(lua_dir: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
    """
    批量获取所有游戏的 DLC 并添加
    
    Args:
        lua_dir: Lua 文件所在目录 (stplug-in 目录)
        progress_callback: 进度回调函数
        
    Returns:
        {"success": bool, "total_games": int, "total_dlc": int, "total_added": int, "message": str}
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
    
    lua_path = pathlib.Path(lua_dir)
    if not lua_path.exists():
        return {"success": False, "total_games": 0, "total_dlc": 0, "total_added": 0,
                "message": f"目录不存在: {lua_dir}"}
    
    # 查找所有 Lua 文件，提取 App ID
    lua_files = list(lua_path.glob("*.lua"))
    
    # 过滤出以数字命名的 Lua 文件（即主游戏的 Lua 文件）
    game_app_ids = []
    for f in lua_files:
        name = f.stem  # 不含扩展名的文件名
        if name.isdigit():
            game_app_ids.append(name)
    
    if not game_app_ids:
        return {"success": True, "total_games": 0, "total_dlc": 0, "total_added": 0,
                "message": "未找到任何已解锁的游戏"}
    
    log(f"找到 {len(game_app_ids)} 个已解锁的游戏，开始获取 DLC...")
    
    total_dlc = 0
    total_added = 0
    processed = 0
    errors = []
    
    for i, app_id in enumerate(game_app_ids):
        try:
            log(f"[{i+1}/{len(game_app_ids)}] 正在处理 {app_id}...")
            
            # 获取 DLC 列表
            dlc_list = get_dlc_list(app_id)
            
            if dlc_list:
                lua_file = os.path.join(lua_dir, f"{app_id}.lua")
                result = add_dlc_to_lua(lua_file, dlc_list)
                
                total_dlc += len(dlc_list)
                total_added += result.get("added", 0)
                
                if result["added"] > 0:
                    log(f"  → 添加 {result['added']} 个 DLC")
            
            processed += 1
            
            # 避免请求过快，简单限流
            if i < len(game_app_ids) - 1:
                time.sleep(0.3)
                
        except Exception as e:
            errors.append(f"{app_id}: {e}")
            continue
    
    message = f"处理完成！共 {processed} 个游戏，获取 {total_dlc} 个 DLC，新增 {total_added} 个"
    if errors:
        message += f"，{len(errors)} 个错误"
    
    log(message)
    
    return {
        "success": True,
        "total_games": processed,
        "total_dlc": total_dlc,
        "total_added": total_added,
        "errors": errors,
        "message": message
    }


def main():
    """命令行入口"""
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python fetch_dlc.py <app_id> [lua_dir]")
        print("      python fetch_dlc.py --all [lua_dir]")
        return
    
    default_lua_dir = r"C:\Program Files (x86)\Steam\config\stplug-in"
    
    def print_progress(msg):
        print(f"  {msg}")
    
    if sys.argv[1] == "--all":
        lua_dir = sys.argv[2] if len(sys.argv) > 2 else default_lua_dir
        result = run_fetch_all(lua_dir, print_progress)
    else:
        app_id = sys.argv[1]
        lua_dir = sys.argv[2] if len(sys.argv) > 2 else default_lua_dir
        result = run_fetch_single(app_id, lua_dir, print_progress)
    
    print(f"\n{result['message']}")


if __name__ == '__main__':
    main()

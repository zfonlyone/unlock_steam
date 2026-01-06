"""
清理无效的 Lua 文件
删除只包含基础 addappid() 而没有密钥的 Lua 文件
同时删除对应的清单文件
支持直接调用和命令行两种方式

直接调用:
    from tools.clean_invalid_lua import run_clean
    result = run_clean(target_dir, auto_delete=False, progress_callback=None)

命令行:
    python clean_invalid_lua.py [目录] [--auto]
"""
import os
import sys
import re
from pathlib import Path


# 匹配 setManifestid(depot_id, "manifest_id") 的正则
MANIFEST_PATTERN = re.compile(r'setManifestid\s*\(\s*(\d+)\s*,\s*["\'](\d+)["\']', re.IGNORECASE)


def get_manifest_ids_from_lua(file_path: str) -> list:
    """
    从 Lua 文件中提取所有清单信息
    返回: [(depot_id, manifest_id), ...]
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            return []
    except:
        return []
    
    matches = MANIFEST_PATTERN.findall(content)
    return matches  # [(depot_id, manifest_id), ...]


def is_invalid_lua(file_path: str) -> tuple:
    """
    检查 Lua 文件是否无效
    返回: (文件路径, 是否无效, 原因, [(depot_id, manifest_id), ...])
    """
    filename = os.path.basename(file_path)
    
    # 保护关键文件
    if filename.lower() in ['steamtools.lua', 'greenluma_config.lua']:
        return (file_path, False, "系统关键文件", [])
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            return (file_path, False, "无法读取", [])
    except:
        return (file_path, False, "无法读取", [])
    
    # 提取清单信息（无论是否有效都要提取）
    manifest_ids = MANIFEST_PATTERN.findall(content)
    
    lines = [l.strip() for l in content.split('\n') if l.strip() and not l.strip().startswith('--')]
    
    if not lines:
        return (file_path, True, "空文件", manifest_ids)
    
    if 'UnlockApp' in content or 'CSharpAPIWrapper' in content:
        return (file_path, True, "错误格式", manifest_ids)
    
    has_any_addappid = 'addappid(' in content.lower()
    if not has_any_addappid:
        return (file_path, True, "不含 addappid", manifest_ids)
    
    # 检查是否有有效的密钥
    has_key = False
    for line in lines:
        if re.search(r'addappid\s*\(\s*\d+\s*,\s*\d+\s*,\s*"', line, re.IGNORECASE):
            has_key = True
            break
        if re.search(r'addappid\s*\(\s*\d+\s*,\s*\d+\s*,\s*\'', line, re.IGNORECASE):
            has_key = True
            break
    
    if not has_key:
        return (file_path, True, "无有效密钥", manifest_ids)
    
    return (file_path, False, "有效文件", manifest_ids)


def find_lua_files(directory: str, progress_callback=None) -> list:
    """快速查找所有 Lua 文件"""
    lua_files = []
    count = 0
    
    try:
        stack = [directory]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.is_file():
                            if entry.name.lower().endswith('.lua'):
                                lua_files.append(entry.path)
                        elif entry.is_dir():
                            stack.append(entry.path)
                        count += 1
                        if count % 1000 == 0 and progress_callback:
                            progress_callback(f"已扫描 {count} 个对象...")
            except PermissionError:
                continue
    except Exception as e:
        if progress_callback:
            progress_callback(f"扫描出错: {e}")
    
    return lua_files


def find_depotcache_dir(stplugin_dir: str) -> str:
    """
    根据 stplug-in 目录找到 depotcache 目录
    stplug-in 在 Steam/config/stplug-in
    depotcache 在 Steam/config/depotcache
    """
    stplugin_path = Path(stplugin_dir)
    # 向上两级找到 config 目录
    if stplugin_path.name == "stplug-in":
        config_dir = stplugin_path.parent
        depotcache = config_dir / "depotcache"
        if depotcache.exists():
            return str(depotcache)
    return ""


def run_clean(target_dir: str, auto_delete: bool = False, progress_callback=None) -> dict:
    """
    清理无效的 Lua 文件并删除对应清单
    
    Args:
        target_dir: 目标目录
        auto_delete: 是否自动删除
        progress_callback: 进度回调函数 callback(message)
        
    Returns:
        {
            "success": bool,
            "total": int,
            "invalid": [(file_path, reason), ...],
            "deleted": int,
            "manifests_deleted": int,
            "message": str
        }
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg, flush=True)
    
    if not os.path.exists(target_dir):
        return {"success": False, "total": 0, "invalid": [], "deleted": 0, 
                "manifests_deleted": 0, "message": f"目录不存在: {target_dir}"}
    
    log(f"开始扫描目录: {target_dir}")
    
    # 查找 depotcache 目录
    depotcache_dir = find_depotcache_dir(target_dir)
    if depotcache_dir:
        log(f"清单目录: {depotcache_dir}")
    
    # 查找所有 Lua 文件
    if os.path.isfile(target_dir):
        lua_files = [target_dir]
    else:
        lua_files = find_lua_files(target_dir, log)
    
    if not lua_files:
        return {"success": True, "total": 0, "invalid": [], "deleted": 0, 
                "manifests_deleted": 0, "message": "未找到任何 Lua 文件"}
    
    log(f"找到 {len(lua_files)} 个 Lua 文件，开始检查...")
    
    # 逐个检查文件
    invalid_files = []  # [(file_path, reason, manifest_ids), ...]
    
    for i, file_path in enumerate(lua_files):
        result = is_invalid_lua(file_path)
        if result[1]:  # 无效
            invalid_files.append((result[0], result[2], result[3]))  # (path, reason, manifest_ids)
        
        if (i + 1) % 500 == 0:
            log(f"已检查 {i + 1}/{len(lua_files)} 个文件...")
    
    if not invalid_files:
        return {"success": True, "total": len(lua_files), "invalid": [], "deleted": 0, 
                "manifests_deleted": 0, "message": f"检查完成，{len(lua_files)} 个文件均有效"}
    
    log(f"发现 {len(invalid_files)} 个无效文件:")
    for fp, reason, _ in invalid_files[:10]:
        log(f"  {os.path.basename(fp)} - {reason}")
    if len(invalid_files) > 10:
        log(f"  ... 还有 {len(invalid_files) - 10} 个")
    
    # 统计清单
    total_manifests = sum(len(m) for _, _, m in invalid_files)
    if total_manifests > 0:
        log(f"关联的清单文件: {total_manifests} 个")
    
    # 是否自动删除
    deleted = 0
    manifests_deleted = 0
    
    if auto_delete:
        log(f"正在删除 {len(invalid_files)} 个无效文件...")
        
        for fp, _, manifest_ids in invalid_files:
            # 删除 Lua 文件
            try:
                os.remove(fp)
                deleted += 1
            except Exception as e:
                log(f"删除失败: {os.path.basename(fp)}")
                continue
            
            # 删除对应的清单文件
            if depotcache_dir and manifest_ids:
                for depot_id, manifest_id in manifest_ids:
                    manifest_file = os.path.join(depotcache_dir, f"{depot_id}_{manifest_id}.manifest")
                    if os.path.exists(manifest_file):
                        try:
                            os.remove(manifest_file)
                            manifests_deleted += 1
                        except:
                            pass
        
        log(f"已删除 {deleted} 个 Lua 文件，{manifests_deleted} 个清单文件")
    else:
        log(f"提示: 设置 auto_delete=True 可自动删除")
    
    return {
        "success": True, 
        "total": len(lua_files), 
        "invalid": [(fp, reason) for fp, reason, _ in invalid_files], 
        "deleted": deleted, 
        "manifests_deleted": manifests_deleted,
        "message": f"发现 {len(invalid_files)} 个无效文件" + 
                   (f"，已删除 {deleted} 个 Lua 和 {manifests_deleted} 个清单" if auto_delete else "")
    }


def main():
    """命令行入口"""
    auto_mode = "--auto" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--auto"]
    
    if args:
        search_dir = ' '.join(args).strip('"').strip("'")
    else:
        search_dir = os.getcwd()
    
    search_dir = os.path.abspath(search_dir)
    result = run_clean(search_dir, auto_delete=auto_mode)
    print(result["message"])


if __name__ == '__main__':
    main()

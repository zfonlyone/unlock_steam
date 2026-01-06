"""
查找没有清单的 Lua 文件
支持直接调用和命令行两种方式

直接调用:
    from tools.find_no_manifest import run_find
    result = run_find(target_dir, progress_callback)

命令行:
    python find_no_manifest.py [目录]
"""
import os
import sys
import re


# 匹配 setManifestid 的正则
MANIFEST_PATTERN = re.compile(r'setManifestid\s*\(', re.IGNORECASE)
# 匹配被注释的 setManifestid
COMMENTED_MANIFEST_PATTERN = re.compile(r'--\s*setManifestid\s*\(', re.IGNORECASE)


def check_has_manifest(file_path: str) -> tuple:
    """
    检查文件是否有有效的清单设置
    返回: (文件路径, 有清单, 被注释)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            return (file_path, False, False)
    except:
        return (file_path, False, False)
    
    # 检查是否有未注释的清单
    has_active = bool(MANIFEST_PATTERN.search(content))
    has_commented = bool(COMMENTED_MANIFEST_PATTERN.search(content))
    
    # 如果有注释的，需要排除它来判断是否有未注释的
    if has_active and has_commented:
        # 移除注释后的内容再检查
        clean_content = re.sub(r'--.*', '', content)
        has_active = bool(MANIFEST_PATTERN.search(clean_content))
    
    return (file_path, has_active, has_commented)


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


def run_find(target_dir: str, progress_callback=None) -> dict:
    """
    查找没有清单的文件
    
    Args:
        target_dir: 目标目录
        progress_callback: 进度回调函数 callback(message)
        
    Returns:
        {
            "success": bool,
            "total": int,
            "no_manifest": [(file_path, is_commented), ...],
            "message": str
        }
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg, flush=True)
    
    if not os.path.exists(target_dir):
        return {"success": False, "total": 0, "no_manifest": [], "message": f"目录不存在: {target_dir}"}
    
    log(f"开始扫描目录: {target_dir}")
    
    # 查找所有 Lua 文件
    if os.path.isfile(target_dir):
        lua_files = [target_dir]
    else:
        lua_files = find_lua_files(target_dir, log)
    
    if not lua_files:
        return {"success": True, "total": 0, "no_manifest": [], "message": "未找到任何 Lua 文件"}
    
    log(f"找到 {len(lua_files)} 个 Lua 文件，开始检查...")
    
    # 逐个检查文件
    no_manifest = []
    
    for i, file_path in enumerate(lua_files):
        result = check_has_manifest(file_path)
        if not result[1]:  # 没有有效清单
            no_manifest.append((result[0], result[2]))  # (路径, 是否被注释)
        
        if (i + 1) % 500 == 0:
            log(f"已检查 {i + 1}/{len(lua_files)} 个文件...")
    
    # 生成结果
    commented = sum(1 for _, c in no_manifest if c)
    no_any = len(no_manifest) - commented
    
    log(f"检查完成: 无清单 {no_any} 个，被注释 {commented} 个")
    
    if no_manifest:
        log(f"无清单文件:")
        for fp, is_commented in no_manifest[:10]:
            status = "(被注释)" if is_commented else "(无)"
            log(f"  {os.path.basename(fp)} {status}")
        if len(no_manifest) > 10:
            log(f"  ... 还有 {len(no_manifest) - 10} 个")
    
    return {"success": True, "total": len(lua_files), "no_manifest": no_manifest, 
            "message": f"检查完成，{len(no_manifest)}/{len(lua_files)} 个文件无有效清单"}


def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        search_dir = ' '.join(sys.argv[1:]).strip('"').strip("'")
    else:
        search_dir = os.getcwd()
    
    search_dir = os.path.abspath(search_dir)
    result = run_find(search_dir)
    print(result["message"])


if __name__ == '__main__':
    main()

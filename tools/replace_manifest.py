"""
禁用固定清单 - 将 Lua 中的 setManifestid 改为 --setManifestid
支持直接调用和命令行两种方式

直接调用:
    from tools.replace_manifest import run_replace
    result = run_replace(target_dir, progress_callback)

命令行:
    python replace_manifest.py [目录]
"""
import os
import sys
import re


def replace_in_file(file_path: str) -> tuple:
    """
    替换文件中的 setManifestid 为 --setManifestid
    返回: (文件路径, 是否修改, 修改数量)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            return (file_path, False, 0)
    except:
        return (file_path, False, 0)
    
    # 计算替换前后的数量
    # 只替换没有 -- 前缀的 setManifestid
    pattern = r'(?<!--)setManifestid'
    matches = len(re.findall(pattern, content))
    
    if matches == 0:
        return (file_path, False, 0)
    
    # 执行替换
    new_content = re.sub(pattern, '--setManifestid', content)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        return (file_path, True, matches)
    except:
        return (file_path, False, 0)


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


def run_replace(target_dir: str, progress_callback=None) -> dict:
    """
    运行替换并返回结果
    
    Args:
        target_dir: 目标目录
        progress_callback: 进度回调函数 callback(message)
        
    Returns:
        {
            "success": bool,
            "total": int,
            "modified": int,
            "message": str
        }
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg, flush=True)
    
    if not os.path.exists(target_dir):
        return {"success": False, "total": 0, "modified": 0, "message": f"目录不存在: {target_dir}"}
    
    log(f"开始扫描目录: {target_dir}")
    
    # 查找所有 Lua 文件
    if os.path.isfile(target_dir):
        lua_files = [target_dir]
    else:
        lua_files = find_lua_files(target_dir, log)
    
    if not lua_files:
        return {"success": True, "total": 0, "modified": 0, "message": "未找到任何 Lua 文件"}
    
    log(f"找到 {len(lua_files)} 个 Lua 文件，开始处理...")
    
    # 逐个处理文件
    modified_count = 0
    modified_files = []
    
    for i, file_path in enumerate(lua_files):
        result = replace_in_file(file_path)
        if result[1]:  # 有修改
            modified_count += 1
            modified_files.append((result[0], result[2]))
        
        if (i + 1) % 500 == 0:
            log(f"已处理 {i + 1}/{len(lua_files)} 个文件...")
    
    # 生成结果
    if modified_count > 0:
        log(f"已禁用 {modified_count} 个文件的固定清单:")
        for fp, count in modified_files[:10]:
            log(f"  {os.path.basename(fp)} ({count} 处)")
        if len(modified_files) > 10:
            log(f"  ... 还有 {len(modified_files) - 10} 个")
    
    return {"success": True, "total": len(lua_files), "modified": modified_count, 
            "message": f"处理完成，{modified_count}/{len(lua_files)} 个文件被修改"}


def main():
    """命令行入口"""
    if len(sys.argv) > 1:
        search_dir = ' '.join(sys.argv[1:]).strip('"').strip("'")
    else:
        search_dir = os.getcwd()
    
    search_dir = os.path.abspath(search_dir)
    result = run_replace(search_dir)
    print(result["message"])


if __name__ == '__main__':
    main()

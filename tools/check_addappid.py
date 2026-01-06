"""
检查 Lua 文件是否有非法字符
合并检查 addappid() 和 setManifestid() 两种函数
支持直接调用和命令行两种方式

直接调用:
    from tools.check_addappid import run_check, run_fix
    result = run_check(target_dir, progress_callback)
    fix_result = run_fix(target_dir, progress_callback)

命令行:
    python check_addappid.py [目录]
    python check_addappid.py [目录] --fix
"""
import os
import sys
import re

# 允许的字符: 数字、字母、逗号、引号、空格
ALLOWED_PATTERN = re.compile(r'^[a-zA-Z0-9,\s"\']+$')
ALLOWED_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789,"\' ')

# 匹配 addappid(...) 和 setManifestid(...) 的内容
ADDAPPID_PATTERN = re.compile(r'addappid\s*\(([^)]*)\)')
SETMANIFEST_PATTERN = re.compile(r'setManifestid\s*\(([^)]*)\)')


def check_file(file_path: str) -> tuple:
    """
    检查文件中的函数是否包含非法字符
    返回: (文件路径, 是否有问题, addappid问题列表, setManifestid问题列表)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='gbk') as f:
                content = f.read()
        except:
            return (file_path, False, [], [])
    except:
        return (file_path, False, [], [])
    
    addappid_issues = []
    setmanifest_issues = []
    
    # 检查 addappid()
    for match in ADDAPPID_PATTERN.findall(content):
        if not ALLOWED_PATTERN.match(match):
            illegal_chars = [c for c in match if c not in ALLOWED_CHARS]
            if illegal_chars:
                addappid_issues.append({
                    'content': match[:50],
                    'illegal_chars': list(set(illegal_chars))
                })
    
    # 检查 setManifestid()
    for match in SETMANIFEST_PATTERN.findall(content):
        if not ALLOWED_PATTERN.match(match):
            illegal_chars = [c for c in match if c not in ALLOWED_CHARS]
            if illegal_chars:
                setmanifest_issues.append({
                    'content': match[:50],
                    'illegal_chars': list(set(illegal_chars))
                })
    
    has_issues = len(addappid_issues) > 0 or len(setmanifest_issues) > 0
    return (file_path, has_issues, addappid_issues, setmanifest_issues)


def fix_file(file_path: str) -> tuple:
    """
    修复单个文件中的非法字符
    返回: (文件路径, 是否修改, 修复数量)
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
    
    original_content = content
    fix_count = 0
    
    # 清理 addappid() 内容
    def clean_addappid(match):
        nonlocal fix_count
        inner = match.group(1)
        cleaned = ''.join(c for c in inner if c in ALLOWED_CHARS)
        if inner != cleaned:
            fix_count += 1
        return f'addappid({cleaned})'
    
    # 清理 setManifestid() 内容
    def clean_setmanifest(match):
        nonlocal fix_count
        inner = match.group(1)
        cleaned = ''.join(c for c in inner if c in ALLOWED_CHARS)
        if inner != cleaned:
            fix_count += 1
        return f'setManifestid({cleaned})'
    
    content = ADDAPPID_PATTERN.sub(clean_addappid, content)
    content = SETMANIFEST_PATTERN.sub(clean_setmanifest, content)
    
    if content != original_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return (file_path, True, fix_count)
        except:
            return (file_path, False, 0)
    
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


def run_check(target_dir: str, progress_callback=None) -> dict:
    """
    运行检查并返回结果
    
    Args:
        target_dir: 目标目录
        progress_callback: 进度回调函数 callback(message)
        
    Returns:
        {
            "success": bool,
            "total": int,
            "problems": [(file_path, addappid_issues, setmanifest_issues), ...],
            "message": str
        }
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg, flush=True)
    
    if not os.path.exists(target_dir):
        return {"success": False, "total": 0, "problems": [], "message": f"目录不存在: {target_dir}"}
    
    log(f"开始扫描目录: {target_dir}")
    
    # 查找所有 Lua 文件
    if os.path.isfile(target_dir):
        lua_files = [target_dir]
    else:
        lua_files = find_lua_files(target_dir, log)
    
    if not lua_files:
        return {"success": True, "total": 0, "problems": [], "message": "未找到任何 Lua 文件"}
    
    log(f"找到 {len(lua_files)} 个 Lua 文件，开始检查...")
    
    # 逐个检查文件
    problems = []
    addappid_count = 0
    setmanifest_count = 0
    
    for i, file_path in enumerate(lua_files):
        result = check_file(file_path)
        if result[1]:  # 有问题
            problems.append((result[0], result[2], result[3]))
            addappid_count += len(result[2])
            setmanifest_count += len(result[3])
        
        if (i + 1) % 500 == 0:
            log(f"已检查 {i + 1}/{len(lua_files)} 个文件...")
    
    # 生成结果
    if problems:
        log(f"发现 {len(problems)} 个有问题的文件:")
        log(f"  addappid 问题: {addappid_count} 处")
        log(f"  setManifestid 问题: {setmanifest_count} 处")
        for fp, add_issues, set_issues in problems[:5]:
            log(f"  {os.path.basename(fp)}")
        if len(problems) > 5:
            log(f"  ... 还有 {len(problems) - 5} 个")
        
        return {
            "success": True, 
            "total": len(lua_files), 
            "problems": problems,
            "addappid_count": addappid_count,
            "setmanifest_count": setmanifest_count,
            "message": f"发现 {len(problems)} 个问题文件 (addappid: {addappid_count}, setManifestid: {setmanifest_count})"
        }
    else:
        log(f"检查完成，共 {len(lua_files)} 个文件，未发现问题")
        return {"success": True, "total": len(lua_files), "problems": [], 
                "message": f"检查完成，{len(lua_files)} 个文件均正常"}


def run_fix(target_dir: str, progress_callback=None) -> dict:
    """
    修复所有有问题的文件
    
    Args:
        target_dir: 目标目录
        progress_callback: 进度回调函数 callback(message)
        
    Returns:
        {
            "success": bool,
            "total": int,
            "fixed": int,
            "message": str
        }
    """
    def log(msg):
        if progress_callback:
            progress_callback(msg)
        print(msg, flush=True)
    
    if not os.path.exists(target_dir):
        return {"success": False, "total": 0, "fixed": 0, "message": f"目录不存在: {target_dir}"}
    
    log(f"开始扫描目录: {target_dir}")
    
    # 查找所有 Lua 文件
    if os.path.isfile(target_dir):
        lua_files = [target_dir]
    else:
        lua_files = find_lua_files(target_dir, log)
    
    if not lua_files:
        return {"success": True, "total": 0, "fixed": 0, "message": "未找到任何 Lua 文件"}
    
    log(f"找到 {len(lua_files)} 个 Lua 文件，开始修复...")
    
    # 逐个修复文件
    fixed_count = 0
    total_fixes = 0
    
    for i, file_path in enumerate(lua_files):
        result = fix_file(file_path)
        if result[1]:  # 有修改
            fixed_count += 1
            total_fixes += result[2]
            log(f"  已修复: {os.path.basename(file_path)} ({result[2]} 处)")
        
        if (i + 1) % 500 == 0:
            log(f"已处理 {i + 1}/{len(lua_files)} 个文件...")
    
    return {
        "success": True, 
        "total": len(lua_files), 
        "fixed": fixed_count,
        "total_fixes": total_fixes,
        "message": f"修复完成，{fixed_count}/{len(lua_files)} 个文件被修改，共 {total_fixes} 处"
    }


def main():
    """命令行入口"""
    fix_mode = "--fix" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    
    if args:
        search_dir = ' '.join(args).strip('"').strip("'")
    else:
        search_dir = os.getcwd()
    
    search_dir = os.path.abspath(search_dir)
    
    if fix_mode:
        result = run_fix(search_dir)
    else:
        result = run_check(search_dir)
    
    print(result["message"])


if __name__ == '__main__':
    main()

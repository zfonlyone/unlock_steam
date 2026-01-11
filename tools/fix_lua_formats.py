import os
import re
import pathlib
from typing import Dict, Any, List, Optional, Callable, Tuple


def run_fix_formats(lua_dir: str, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    识别并修复 Lua 文件中 addappid 的格式问题：
    1. addappid(id, x, "None") -> addappid(id)
    2. addappid(id, x, "hash") -> 中间参数从 0 开始递增
    3. 保留其他所有内容（注释、setManifestid 等）
    4. 仅处理数字命名的 Lua 文件
    """
    lua_path = pathlib.Path(lua_dir)
    if not lua_path.exists():
        return {"success": False, "message": f"目录不存在: {lua_dir}"}

    # 匹配 addappid(id, num, "None") 格式
    pattern_none = re.compile(
        r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*["\']None["\']\s*\)',
        re.IGNORECASE
    )
    
    # 匹配 addappid(id, num, "hash") 格式 (包括 0)
    pattern_hash = re.compile(
        r'addappid\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(["\'][a-fA-F0-9]+["\'])\s*\)'
    )

    fixed_files = 0
    total_files = 0
    total_replacements = 0

    # 只处理数字命名的 Lua 文件
    lua_files = [f for f in lua_path.glob("*.lua") if f.stem.isdigit()]
    total_count = len(lua_files)
    
    for i, file_path in enumerate(lua_files):
        try:
            total_files += 1
            if progress_callback and i % 100 == 0:
                progress_callback(f"正在检查 ({i}/{total_count}): {file_path.name}")
            
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            original_content = content
            file_replacements = 0
            
            # 修复 1: addappid(id, x, "None") -> addappid(id)
            def replace_none(match):
                nonlocal file_replacements
                file_replacements += 1
                app_id = match.group(1)
                return f'addappid({app_id})'
            
            content = pattern_none.sub(replace_none, content)
            
            # 修复 2: addappid(id, x, "hash") -> addappid(id, 递增序号, "hash")
            # 使用计数器生成递增序号
            counter = [0]  # 使用列表以便在闭包中修改
            
            def replace_hash_sequential(match):
                nonlocal file_replacements
                app_id = match.group(1)
                old_num = match.group(2)
                hash_val = match.group(3)
                new_num = counter[0]
                counter[0] += 1
                
                if old_num != str(new_num):
                    file_replacements += 1
                
                return f'addappid({app_id}, {new_num}, {hash_val})'
            
            content = pattern_hash.sub(replace_hash_sequential, content)
            
            # 只有内容变化时才写入
            if content != original_content:
                file_path.write_text(content, encoding='utf-8')
                fixed_files += 1
                total_replacements += file_replacements
                
        except Exception as e:
            if progress_callback:
                progress_callback(f"处理文件 {file_path.name} 出错: {e}")

    result_msg = f"扫描完成！共处理 {total_files} 个文件。\n修复了 {fixed_files} 个文件，共 {total_replacements} 处修正。"
    return {
        "success": True, 
        "message": result_msg,
        "fixed_count": fixed_files,
        "replacement_count": total_replacements
    }

if __name__ == "__main__":
    # 默认路径
    TARGET = r"C:\Program Files (x86)\Steam\config\stplug-in"
    print(f"--- Lua 格式修复工具 ---")
    print(f"目标目录: {TARGET}")
    
    def simple_progress(msg):
        print(f"  {msg}")
        
    res = run_fix_formats(TARGET, simple_progress)
    print("\n" + res["message"])


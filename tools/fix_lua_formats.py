import os
import re
import pathlib
from typing import Dict, Any, List, Optional, Callable

def run_fix_formats(lua_dir: str, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    识别并修复 Lua 文件中 addappid 的格式问题：
    1. addappid(id, 1, "None") -> addappid(id)
    2. addappid(id, 1, "hash") -> addappid(id, 0, "hash")
    """
    lua_path = pathlib.Path(lua_dir)
    if not lua_path.exists():
        return {"success": False, "message": f"目录不存在: {lua_dir}"}

    # 1. 直接匹配 addappid(id, x, "None") -> addappid(id)
    # 支持带引号或不带引号的 None，支持各种空格
    pattern_none = re.compile(
        r'addappid\s*\(\s*(\d+)\s*,\s*\d+\s*,\s*["\']None["\']\s*\)', 
        re.IGNORECASE
    )
    
    # 2. 匹配 addappid(id, 1, "hash") -> addappid(id, 0, "hash")
    # 只要中间不是 0 且结尾是引号包裹的 hex 字符串
    pattern_hash = re.compile(
        r'addappid\s*\(\s*(\d+)\s*,\s*([1-9]\d*)\s*,\s*(["\'][a-fA-F0-9]+["\'])\s*\)'
    )

    fixed_files = 0
    total_files = 0
    total_replacements = 0

    lua_files = list(lua_path.glob("*.lua"))
    total_count = len(lua_files)
    
    for i, file_path in enumerate(lua_files):
        try:
            total_files += 1
            if progress_callback and i % 100 == 0:
                progress_callback(f"正在检查 ({i}/{total_count}): {file_path.name}")
            
            content = file_path.read_text(encoding='utf-8', errors='ignore')
            new_content = content
            
            # 第一阶段：修复 None
            new_content, count_none = pattern_none.subn(r'addappid(\1)', new_content)
            
            # 第二阶段：修复中间值为 0
            new_content, count_hash = pattern_hash.subn(r'addappid(\1, 0, \3)', new_content)
            
            if new_content != content:
                file_path.write_text(new_content, encoding='utf-8')
                fixed_files += 1
                total_replacements += (count_none + count_hash)
        except Exception as e:
            if progress_callback:
                progress_callback(f"处理文件 {file_path.name} 出错: {e}")

    result_msg = f"扫描完成！共处理 {total_files} 个文件。\n修复了 {fixed_files} 个文件，共执行 {total_replacements} 处替换。"
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

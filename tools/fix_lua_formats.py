import os
import re
import pathlib
from typing import Dict, Any, List, Optional, Callable

def run_fix_formats(lua_dir: str, progress_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
    """
    识别并修复 Lua 文件中 addappid 的格式问题：
    1. addappid(id, 1, "None") -> 移除或转为 addappid(id)
    2. addappid(id, x, "hash") -> addappid(id, i, "hash")，i从0开始递增
    3. id为主键，相同id只保留含有hash的条目
    4. 相同的(id, hash)组合只保留一个
    """
    lua_path = pathlib.Path(lua_dir)
    if not lua_path.exists():
        return {"success": False, "message": f"目录不存在: {lua_dir}"}

    # 匹配所有 addappid 调用的通用模式
    # 支持: addappid(id), addappid(id, num), addappid(id, num, "hash")
    pattern_all = re.compile(
        r'addappid\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*(?:,\s*(["\'][^"\']*["\']))?\s*)?\)',
        re.IGNORECASE
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
            
            # 收集所有 addappid 条目，用 dict 以 id 为主键
            # 值为 (hash, original_match) 或 None
            id_entries: Dict[str, Optional[str]] = {}  # id -> hash (or None if no hash)
            seen_id_hash: set = set()  # 用于去重 (id, hash) 组合
            
            matches = list(pattern_all.finditer(content))
            if not matches:
                continue
            
            for match in matches:
                app_id = match.group(1)
                hash_val = match.group(3)  # 可能是 None
                
                # 去除引号获取实际 hash 值
                actual_hash = None
                if hash_val:
                    actual_hash = hash_val.strip('"\'')
                    # 如果是 "None"，视为无效 hash
                    if actual_hash.lower() == 'none':
                        actual_hash = None
                
                if actual_hash:
                    # 有有效的 hash
                    key = (app_id, actual_hash)
                    if key in seen_id_hash:
                        # 相同的 (id, hash) 组合，跳过
                        continue
                    seen_id_hash.add(key)
                    id_entries[app_id] = actual_hash
                else:
                    # 没有有效 hash，只有当这个 id 还没有记录时才添加
                    if app_id not in id_entries:
                        id_entries[app_id] = None
            
            # 生成新的内容：按 id 顺序，中间数从 0 开始递增
            new_lines = []
            counter = 0
            for app_id, hash_val in id_entries.items():
                if hash_val:
                    # 有 hash: addappid(id, i, "hash")
                    new_lines.append(f'addappid({app_id}, {counter}, "{hash_val}")')
                else:
                    # 无 hash: addappid(id)
                    new_lines.append(f'addappid({app_id})')
                counter += 1
            
            new_content = '\n'.join(new_lines) + '\n'
            
            if new_content.strip() != content.strip():
                file_path.write_text(new_content, encoding='utf-8')
                fixed_files += 1
                total_replacements += len(id_entries)
        except Exception as e:
            if progress_callback:
                progress_callback(f"处理文件 {file_path.name} 出错: {e}")

    result_msg = f"扫描完成！共处理 {total_files} 个文件。\n修复了 {fixed_files} 个文件，共 {total_replacements} 个 addappid 条目。"
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

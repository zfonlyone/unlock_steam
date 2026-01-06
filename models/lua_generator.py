"""
Lua 脚本生成器
生成和修改 Steam 解锁 Lua 脚本
"""
import os
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path


class LuaGenerator:
    """Lua 脚本生成器"""
    
    def __init__(self, stplugin_path: str = ""):
        """初始化
        
        Args:
            stplugin_path: stplug-in 目录路径
        """
        self.stplugin_path = stplugin_path
    
    def set_path(self, path: str):
        """设置 stplug-in 路径"""
        self.stplugin_path = path
    
    def generate_lua_content(self, app_id: str, depots: Dict[str, dict]) -> str:
        """生成 Lua 脚本内容
        
        Args:
            app_id: 游戏 AppID
            depots: depot 信息字典 {depot_id: {manifest_id, decryption_key}}
            
        Returns:
            Lua 脚本内容
        """
        lines = []
        
        # 添加主 appid
        lines.append(f"addappid({app_id})")
        
        # 添加每个 depot
        for depot_id, info in depots.items():
            key = info.get('decryption_key', '')
            manifest_id = info.get('manifest_id', '')
            
            if key:
                lines.append(f'addappid({depot_id},0,"{key}")')
            else:
                lines.append(f'addappid({depot_id})')
            
            if manifest_id:
                lines.append(f'setManifestid({depot_id},"{manifest_id}")')
        
        return '\n'.join(lines)
    
    def save_lua_file(self, app_id: str, content: str) -> Tuple[bool, str]:
        """保存 Lua 文件到 stplug-in 目录
        
        Args:
            app_id: 游戏 AppID
            content: Lua 内容
            
        Returns:
            (是否成功, 消息)
        """
        if not self.stplugin_path:
            return False, "stplug-in 路径未设置"
        
        if not os.path.exists(self.stplugin_path):
            return False, f"目录不存在: {self.stplugin_path}"
        
        try:
            file_path = os.path.join(self.stplugin_path, f"{app_id}.lua")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, file_path
        except Exception as e:
            return False, str(e)
    
    def read_lua_file(self, app_id: str) -> Optional[str]:
        """读取 Lua 文件内容
        
        Args:
            app_id: 游戏 AppID
            
        Returns:
            文件内容或 None
        """
        if not self.stplugin_path:
            return None
        
        file_path = os.path.join(self.stplugin_path, f"{app_id}.lua")
        if not os.path.exists(file_path):
            return None
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None
    
    def update_manifest_id(self, app_id: str, depot_id: str, new_manifest_id: str) -> Tuple[bool, str]:
        """更新 Lua 文件中的 manifest ID
        
        Args:
            app_id: 游戏 AppID
            depot_id: Depot ID
            new_manifest_id: 新的 Manifest ID
            
        Returns:
            (是否成功, 消息)
        """
        content = self.read_lua_file(app_id)
        if content is None:
            return False, "文件不存在"
        
        # 匹配 setManifestid(depot_id, "xxx") 或 --setManifestid(...)
        pattern = rf'(--)?setManifestid\s*\(\s*{depot_id}\s*,\s*["\']([^"\']*)["\'][^)]*\)'
        
        def replace_manifest(match):
            prefix = match.group(1) or ''  # 保留注释前缀
            return f'{prefix}setManifestid({depot_id},"{new_manifest_id}")'
        
        new_content, count = re.subn(pattern, replace_manifest, content)
        
        if count == 0:
            # 如果没有找到，添加新行
            new_content = content.rstrip() + f'\nsetManifestid({depot_id},"{new_manifest_id}")'
        
        return self.save_lua_file(app_id, new_content)
    
    def toggle_set_manifest(self, app_id: str, enable: bool = True) -> Tuple[bool, str]:
        """切换 setManifestid 的启用/禁用状态
        
        Args:
            app_id: 游戏 AppID
            enable: True=启用, False=禁用(注释)
            
        Returns:
            (是否成功, 消息)
        """
        content = self.read_lua_file(app_id)
        if content is None:
            return False, "文件不存在"
        
        if enable:
            # 取消注释: --setManifestid -> setManifestid
            new_content = re.sub(r'^--setManifestid', 'setManifestid', content, flags=re.MULTILINE)
        else:
            # 添加注释: setManifestid -> --setManifestid
            new_content = re.sub(r'^setManifestid', '--setManifestid', content, flags=re.MULTILINE)
        
        if new_content == content:
            return True, "无需修改"
        
        return self.save_lua_file(app_id, new_content)
    
    def batch_toggle_set_manifest(self, app_ids: List[str], enable: bool = True) -> Dict[str, Tuple[bool, str]]:
        """批量切换 setManifestid 状态
        
        Args:
            app_ids: AppID 列表
            enable: 是否启用
            
        Returns:
            {app_id: (success, message)}
        """
        results = {}
        for app_id in app_ids:
            results[app_id] = self.toggle_set_manifest(app_id, enable)
        return results
    
    def check_lua_validity(self, content: str) -> Tuple[bool, List[str]]:
        """检查 Lua 脚本合法性
        
        Args:
            content: Lua 内容
            
        Returns:
            (是否合法, 问题列表)
        """
        issues = []
        
        # 检查 addappid 参数
        addappid_pattern = re.compile(r'addappid\s*\(([^)]*)\)')
        for match in addappid_pattern.finditer(content):
            params = match.group(1)
            # 只允许: 数字、字母、逗号、引号、空格
            if not re.match(r'^[a-zA-Z0-9,\s"\']+$', params):
                illegal = [c for c in params if not re.match(r'[a-zA-Z0-9,\s"\']', c)]
                issues.append(f"addappid 包含非法字符: {set(illegal)}")
        
        # 检查 setManifestid 参数
        setmanifest_pattern = re.compile(r'setManifestid\s*\(([^)]*)\)')
        for match in setmanifest_pattern.finditer(content):
            params = match.group(1)
            if not re.match(r'^[a-zA-Z0-9,\s"\']+$', params):
                illegal = [c for c in params if not re.match(r'[a-zA-Z0-9,\s"\']', c)]
                issues.append(f"setManifestid 包含非法字符: {set(illegal)}")
        
        return len(issues) == 0, issues
    
    def fix_lua_content(self, content: str) -> str:
        """修复 Lua 脚本中的非法字符
        
        Args:
            content: 原始内容
            
        Returns:
            修复后的内容
        """
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789,"\' ')
        
        def clean_params(match):
            func_name = match.group(1)
            params = match.group(2)
            cleaned = ''.join(c for c in params if c in allowed_chars)
            return f'{func_name}({cleaned})'
        
        # 清理 addappid 参数
        content = re.sub(r'(addappid)\s*\(([^)]*)\)', clean_params, content)
        # 清理 setManifestid 参数
        content = re.sub(r'(setManifestid)\s*\(([^)]*)\)', clean_params, content)
        
        return content
    
    def list_lua_files(self) -> List[str]:
        """列出 stplug-in 目录下的所有 Lua 文件
        
        Returns:
            AppID 列表
        """
        if not self.stplugin_path or not os.path.exists(self.stplugin_path):
            return []
        
        app_ids = []
        for file in os.listdir(self.stplugin_path):
            if file.endswith('.lua'):
                app_id = file[:-4]  # 移除 .lua 后缀
                if app_id.isdigit():
                    app_ids.append(app_id)
        return app_ids

import os
import json
from typing import Dict, Any, Optional, List


class ConfigModel:
    """应用程序配置管理模型 - 支持多仓库和 API 密钥"""
    
    def __init__(self, config_file: str = "config.json"):
        """初始化配置模型
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """从文件加载配置
        
        Returns:
            配置字典
        """
        default_config = {
            "steam_path": "",
            "manifest_repo_path": "",
            "preferred_unlock_tool": "steamtools",
            "lua_path": "",  # stplug-in 目录
            "repositories": [],  # 多仓库配置
            "api_key": "",  # ManifestHub API 密钥
            "view_mode": "grid",  # grid 或 list
            "theme": "dark",
            "save_game_names": False,  # 是否保存游戏名称 (默认不开启)
            "save_extra_data": False   # 是否保存游戏密钥和清单 ID 等额外数据 (默认不开启)
        }
        
        if not os.path.exists(self.config_file):
            return default_config
            
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
                # 合并默认配置和加载的配置
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                return config
        except:
            return default_config
    
    def save_config(self) -> bool:
        """保存配置到文件
        
        Returns:
            是否保存成功
        """
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False
    
    def get_config(self) -> Dict[str, Any]:
        """获取完整配置"""
        return self.config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取指定配置项"""
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any, auto_save: bool = False) -> None:
        """设置指定配置项"""
        self.config[key] = value
        if auto_save:
            self.save_config()
    
    # ===== 多仓库管理 =====
    
    def get_repositories(self) -> List[Dict[str, Any]]:
        """获取所有仓库配置"""
        return self.config.get("repositories", [])
    
    def add_repository(self, name: str, repo_type: str, path: str = "", 
                       enabled: bool = True, auto_save: bool = False) -> None:
        """添加仓库
        
        Args:
            name: 仓库名称
            repo_type: 类型 (local/remote)
            path: 本地路径（local 类型）
            enabled: 是否启用
            auto_save: 是否自动保存
        """
        repos = self.get_repositories()
        
        # 检查是否已存在
        for repo in repos:
            if repo.get("name") == name:
                repo.update({"type": repo_type, "path": path, "enabled": enabled})
                if auto_save:
                    self.save_config()
                return
        
        # 添加新仓库
        repos.append({
            "name": name,
            "type": repo_type,
            "path": path,
            "enabled": enabled
        })
        self.config["repositories"] = repos
        if auto_save:
            self.save_config()
    
    def remove_repository(self, name: str, auto_save: bool = False) -> bool:
        """删除仓库"""
        repos = self.get_repositories()
        new_repos = [r for r in repos if r.get("name") != name]
        if len(new_repos) != len(repos):
            self.config["repositories"] = new_repos
            if auto_save:
                self.save_config()
            return True
        return False
    
    def get_repositories(self) -> List[Dict[str, Any]]:
        """获取所有仓库配置，如果为空则返回默认仓库"""
        repos = self.config.get("repositories", [])
        if not repos:
            # 返回默认的 ManifestHub 远程仓库
            return [{
                "name": "ManifestHub",
                "type": "remote",
                "url": "https://github.com/SteamAutoCracks/ManifestHub",
                "enabled": True
            }]
        return repos
    
    def get_enabled_repositories(self) -> List[Dict[str, Any]]:
        """获取所有启用的仓库"""
        return [r for r in self.get_repositories() if r.get("enabled", True)]
    
    # ===== API 密钥管理 =====
    
    def get_api_key(self) -> str:
        """获取 API 密钥"""
        return self.config.get("api_key", "")
    
    def set_api_key(self, api_key: str, auto_save: bool = False) -> None:
        """设置 API 密钥"""
        self.config["api_key"] = api_key
        if auto_save:
            self.save_config()
    
    # ===== Lua 路径管理 =====
    
    def get_lua_path(self) -> str:
        """获取 stplug-in 目录路径"""
        lua_path = self.config.get("lua_path", "")
        if lua_path:
            return lua_path
        
        # 尝试从 steam_path 推断
        steam_path = self.config.get("steam_path", "")
        if steam_path:
            default_path = os.path.join(steam_path, "config", "stplug-in")
            if os.path.exists(default_path):
                return default_path
        return ""
    
    def set_lua_path(self, path: str, auto_save: bool = False) -> None:
        """设置 stplug-in 目录路径"""
        self.config["lua_path"] = path
        if auto_save:
            self.save_config()
    
    # ===== 视图模式 =====
    
    def get_view_mode(self) -> str:
        """获取视图模式 (grid/list)"""
        return self.config.get("view_mode", "grid")
    
    def set_view_mode(self, mode: str, auto_save: bool = False) -> None:
        """设置视图模式"""
        if mode in ("grid", "list"):
            self.config["view_mode"] = mode
            if auto_save:
                self.save_config()
    
    # ===== 验证 =====
    
    def is_valid_config(self) -> bool:
        """检查配置是否有效
        
        注意: manifest_repo_path 是可选的，留空时使用 GitHub 仓库
        """
        steam_path = self.get("steam_path", "")
        
        # Steam 路径是必须的
        if not steam_path:
            return False
        
        steam_path = os.path.normpath(steam_path)
        if not os.path.exists(steam_path):
            return False
        
        # 本地仓库路径是可选的
        repo_path = self.get("manifest_repo_path", "")
        if repo_path:
            repo_path = os.path.normpath(repo_path)
            git_dir = os.path.join(repo_path, ".git")
            # 如果填了但不是有效仓库，返回 False
            if not os.path.exists(git_dir):
                return False
        
        # 只有 Steam 路径有效即可
        return True

    
    def validate_paths(self) -> Dict[str, bool]:
        """验证所有路径
        
        Returns:
            {路径名: 是否有效}
        """
        results = {}
        
        steam_path = self.get("steam_path", "")
        results["steam_path"] = bool(steam_path and os.path.exists(steam_path))
        
        repo_path = self.get("manifest_repo_path", "")
        if repo_path:
            git_dir = os.path.join(repo_path, ".git")
            results["manifest_repo_path"] = os.path.exists(git_dir)
        else:
            results["manifest_repo_path"] = False
        
        lua_path = self.get_lua_path()
        results["lua_path"] = bool(lua_path and os.path.exists(lua_path))
        
        return results
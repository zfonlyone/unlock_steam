import os
import json
from typing import Dict, Any, Optional

class ConfigModel:
    """应用程序配置管理模型"""
    
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
            "preferred_unlock_tool": "steamtools"
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
        """获取完整配置
        
        Returns:
            配置字典
        """
        return self.config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取指定配置项
        
        Args:
            key: 配置项键名
            default: 默认值
            
        Returns:
            配置项的值
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any, auto_save: bool = False) -> None:
        """设置指定配置项
        
        Args:
            key: 配置项键名
            value: 配置项值
            auto_save: 是否自动保存
        """
        self.config[key] = value
        if auto_save:
            self.save_config()
    
    def is_valid_config(self) -> bool:
        """检查配置是否有效
        
        Returns:
            配置是否有效
        """
        steam_path = self.get("steam_path", "")
        repo_path = self.get("manifest_repo_path", "")
        
        return (
            os.path.exists(steam_path) and 
            os.path.exists(repo_path) and 
            os.path.exists(os.path.join(repo_path, ".git"))
        ) 
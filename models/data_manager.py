import json
import os
import time
import datetime
import copy
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set


class DataManager:
    """管理游戏数据的本地存储(Model层)"""
    
    def __init__(self, data_file: str = "games_data.json"):
        """初始化数据管理器
        
        Args:
            data_file: 数据文件的路径
        """
        self.data_file = data_file
        self.games_data = self._load_data()
        
        # 验证并修复数据文件
        self._validate_and_repair_data()
    
    def _validate_and_repair_data(self):
        """验证并修复数据文件，确保数据完整性"""
        try:
            # 检查游戏数据结构是否完整
            if "games" not in self.games_data:
                self.games_data["games"] = {}
                
            if "last_update" not in self.games_data:
                self.games_data["last_update"] = datetime.datetime.now().isoformat()
        except Exception as e:
            print(f"数据验证错误: {e}")
    
    def _load_data(self) -> Dict[str, Any]:
        """从本地文件加载数据
        
        Returns:
            游戏数据字典
        """
        if not os.path.exists(self.data_file):
            # 如果文件不存在，返回空字典
            return {"games": {}, "last_update": datetime.datetime.now().isoformat()}
            
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # 如果JSON解析错误，尝试修复
            return self._repair_json_file(self.data_file, e)
        except Exception as e:
            print(f"加载数据错误: {e}")
            return {"games": {}, "last_update": datetime.datetime.now().isoformat()}
    
    def _repair_json_file(self, file_path: str, error: json.JSONDecodeError) -> Dict[str, Any]:
        """尝试修复损坏的JSON文件
        
        Args:
            file_path: 文件路径
            error: JSON解析错误
            
        Returns:
            修复后的数据字典
        """
        # 创建备份
        backup_path = f"{file_path}.bak"
        try:
            shutil.copy2(file_path, backup_path)
            print(f"已创建数据文件备份: {backup_path}")
        except Exception as e:
            print(f"创建备份失败: {e}")
        
        # 尝试修复方法1: 忽略错误行
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            lines = content.split("\n")
            error_line = error.lineno - 1
            
            # 移除可能导致错误的行
            if 0 <= error_line < len(lines):
                print(f"尝试修复: 移除第{error_line + 1}行")
                del lines[error_line]
                
                # 写入修复后的内容
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                    
                # 重新加载
                with open(file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            print(f"修复方法1失败: {e}")
        
        # 尝试修复方法2: 提取有效的JSON部分
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 寻找最后一个有效的JSON结构
            last_brace_pos = content.rfind("}")
            if last_brace_pos > 0:
                valid_part = content[:last_brace_pos + 1]
                # 尝试解析
                try:
                    return json.loads(valid_part)
                except Exception:
                    pass
        except Exception as e:
            print(f"修复方法2失败: {e}")
        
        # 如果所有修复方法都失败，返回空数据
        print("无法修复数据文件，使用空数据")
        return {"games": {}, "last_update": datetime.datetime.now().isoformat()}
        
    def save_data(self, silent: bool = False) -> bool:
        """保存数据到本地文件
        
        Args:
            silent: 是否静默保存，不显示消息
            
        Returns:
            是否保存成功
        """
        try:
            # 更新保存时间
            self.games_data["last_update"] = datetime.datetime.now().isoformat()
            
            # 先写入临时文件
            temp_file = f"{self.data_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.games_data, f, ensure_ascii=False, indent=2)
                
            # 如果成功写入临时文件，再替换原文件
            if os.path.exists(self.data_file):
                # 创建备份
                backup_file = f"{self.data_file}.bak"
                try:
                    shutil.copy2(self.data_file, backup_file)
                except Exception as e:
                    if not silent:
                        print(f"创建备份失败: {e}")
            
            # 替换原文件
            shutil.move(temp_file, self.data_file)
            
            if not silent:
                print(f"数据已保存到 {self.data_file}")
                
            return True
                
        except Exception as e:
            if not silent:
                print(f"保存数据失败: {e}")
            return False
    
    def update_game(self, app_id: str, database_name: str, game_name: Optional[str] = None, 
                   is_unlocked: bool = None, auto_save: bool = False) -> None:
        """更新游戏信息
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            game_name: 游戏名称，如果为None则不更新
            is_unlocked: 是否已解锁，如果为None则不更新
            auto_save: 是否自动保存到文件
        """
        # 确保games字典存在
        if "games" not in self.games_data:
            self.games_data["games"] = {}
            
        # 获取现有游戏数据或创建新的
        game = self.games_data["games"].get(app_id, {})
        
        # 更新数据库名称
        databases = game.get("databases", [])
        if database_name and database_name not in databases:
            databases.append(database_name)
            game["databases"] = databases
            
        # 更新游戏名称
        if game_name is not None:
            current_name = game.get("game_name", "")
            # 只有在以下情况下更新游戏名称：
            # 1. 当前名称为空
            # 2. 当前名称以"Game "开头（默认名称）
            # 3. 提供的名称不为空且不是默认名称
            if not current_name or current_name.startswith("Game "):
                game["game_name"] = game_name
            elif game_name and not game_name.startswith("Game "):
                # 如果提供了有意义的非默认名称，覆盖当前名称
                game["game_name"] = game_name
                
        # 更新解锁状态
        if is_unlocked is not None:
            game["is_unlocked"] = is_unlocked
            
        # 存储更新后的游戏数据
        self.games_data["games"][app_id] = game
        
        # 如果需要自动保存，则保存到文件
        if auto_save:
            self.save_data(silent=True)
    
    def get_all_games(self) -> List[Dict[str, Any]]:
        """获取所有游戏信息
        
        Returns:
            游戏信息列表
        """
        games = []
        for app_id, game_data in self.games_data.get("games", {}).items():
            game = copy.deepcopy(game_data)
            game["app_id"] = app_id
            games.append(game)
        return games
    
    def get_game(self, app_id: str) -> Optional[Dict[str, Any]]:
        """获取指定AppID的游戏信息
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            游戏信息字典，如果不存在则返回None
        """
        game = self.games_data.get("games", {}).get(app_id)
        if not game:
            return None
            
        result = copy.deepcopy(game)
        result["app_id"] = app_id
        return result
    
    def set_unlock_status(self, app_id: str, is_unlocked: bool, auto_save: bool = False) -> None:
        """设置游戏的解锁状态
        
        Args:
            app_id: 游戏的AppID
            is_unlocked: 是否已解锁
            auto_save: 是否自动保存到文件
        """
        if "games" not in self.games_data:
            self.games_data["games"] = {}
            
        if app_id in self.games_data["games"]:
            self.games_data["games"][app_id]["is_unlocked"] = is_unlocked
            
            if auto_save:
                self.save_data(silent=True)
                
    def batch_set_unlock_status(self, updates: List[str], auto_save: bool = True) -> int:
        """批量设置多个游戏的解锁状态
        
        Args:
            updates: 游戏更新列表，每项为app_id的元组
            auto_save: 是否自动保存到文件
            
        Returns:
            成功更新的游戏数量
        """
        if "games" not in self.games_data:
            self.games_data["games"] = {}
            
        updated_count = 0
        
        # 批量更新所有游戏的解锁状态
        for app_id in updates:
            if app_id in self.games_data["games"]:
                self.games_data["games"][app_id]["is_unlocked"] = True
                updated_count += 1
                
        # 只保存一次数据，避免多次IO操作
        if auto_save and updated_count > 0:
            self.save_data(silent=True)
            
        return updated_count
    
    def update_games_from_branches(self, branches: List[Tuple[str, str]], silent: bool = False, auto_save: bool = False) -> None:
        """从分支列表更新游戏数据
        
        Args:
            branches: 分支列表，每个元素为(app_id, branch_name)的元组
            silent: 是否静默更新，不显示消息
            auto_save: 是否自动保存到文件
        """
        # 提取所有数据库名称
        database_names = set()
        for app_id, branch_name in branches:
            parts = branch_name.split("/")
            if len(parts) > 1:
                database_name = parts[0]
                database_names.add(database_name)
        
        if not database_names:
            database_names = {"default"}
        
        # 更新游戏数据
        updated_count = 0
        for app_id, branch_name in branches:
            # 从分支名称中提取仓库名称作为数据库名称
            parts = branch_name.split("/")
            database_name = parts[0] if len(parts) > 1 else next(iter(database_names))
            
            # 默认设置游戏名称为空字符串，方便后续获取真实名称
            game_name = ""
            
            # 更新游戏信息
            self.update_game(app_id, database_name, game_name, auto_save=False)
            updated_count += 1
            
        # 保存数据
        if auto_save:
            self.save_data(silent=silent)
            
        if not silent:
            print(f"已更新 {updated_count} 个游戏的数据")
    
    def get_game_databases(self, app_id: str) -> List[str]:
        """获取游戏的数据库列表
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            数据库名称列表
        """
        game = self.get_game(app_id)
        if not game:
            return []
        
        return game.get("databases", [])
    
    def get_steam_game_names(self, app_ids: List[str]) -> Dict[str, str]:
        """获取游戏名称
        
        Args:
            app_ids: AppID列表
            
        Returns:
            以AppID为键，游戏名称为值的字典
        """
        game_names = {}
        
        # 将已有的游戏名称添加到结果中
        for app_id in app_ids:
            game = self.get_game(app_id)
            if game:
                game_names[app_id] = game.get("game_name", f"Game {app_id}")
        
        return game_names
    
    def get_last_update(self) -> Optional[str]:
        """获取最后更新时间
        
        Returns:
            最后更新时间的ISO格式字符串，如果不存在则返回None
        """
        return self.games_data.get("last_update") 
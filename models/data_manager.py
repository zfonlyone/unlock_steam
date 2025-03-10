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
        
        # 标准化的数据结构模板
        self.default_data_structure = {
            "games": {},  # 游戏数据字典，以AppID为键
            "last_update": datetime.datetime.now().isoformat()  # 上次更新时间
        }
        
        # 是否是首次创建
        is_first_creation = not os.path.exists(self.data_file)
        
        # 加载或创建数据
        self.games_data = self._load_data()
        
        # 验证并修复数据文件
        self._validate_and_repair_data()
        
        # 如果数据文件不存在，创建一个标准格式的空数据文件
        if is_first_creation:
            # 添加示例记录，帮助用户理解数据格式
            if len(self.games_data.get("games", {})) == 0:
                # 添加两个示例游戏（知名游戏）
                self.update_game(
                    app_id="730", 
                    database_name="default", 
                    game_name="免费无需解锁Counter-Strike 2", 
                    is_unlocked=False, 
                    auto_save=False
                )
                self.update_game(
                    app_id="570", 
                    database_name="default", 
                    game_name="免费无需解锁Dota 2", 
                    is_unlocked=False, 
                    auto_save=False
                )
                
            # 保存到文件
            self.save_data(silent=True)
            
            print(f"创建了新的数据文件: {self.data_file}")
        
        # 始终保存一次，确保文件格式正确
        else:
            self.save_data(silent=True)
    
    def _validate_and_repair_data(self):
        """验证并修复数据文件，确保数据完整性"""
        try:
            # 确保数据结构包含所有必要的字段
            for key, value in self.default_data_structure.items():
                if key not in self.games_data:
                    self.games_data[key] = copy.deepcopy(value)
            
            # 确保上次更新时间字段是有效的
            if not isinstance(self.games_data.get("last_update"), str):
                self.games_data["last_update"] = datetime.datetime.now().isoformat()
            
            # 确保games字段是字典类型
            if not isinstance(self.games_data.get("games"), dict):
                self.games_data["games"] = {}
        except Exception as e:
            print(f"数据验证错误: {e}")
            # 如果验证过程中出现错误，使用默认数据结构
            self.games_data = dict(self.default_data_structure)
    
    def _load_data(self) -> Dict[str, Any]:
        """从本地文件加载数据
        
        Returns:
            游戏数据字典
        """
        if not os.path.exists(self.data_file):
            # 如果文件不存在，返回默认的数据结构
            return dict(self.default_data_structure)
            
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            # 如果JSON解析错误，尝试修复
            return self._repair_json_file(self.data_file, e)
        except Exception as e:
            print(f"加载数据错误: {e}")
            return dict(self.default_data_structure)
    
    def _repair_json_file(self, file_path: str, error: json.JSONDecodeError) -> Dict[str, Any]:
        """尝试修复损坏的JSON文件
        
        Args:
            file_path: 文件路径
            error: JSON解析错误
            
        Returns:
            修复后的数据或默认数据
        """
        print(f"尝试修复损坏的JSON文件: {file_path}, 错误: {error}")
        
        # 方法1: 尝试使用错误位置之前的内容
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 截取错误位置之前的部分
            valid_part = content[:error.pos]
            # 尝试找到最后一个完整的JSON对象
            last_brace_idx = valid_part.rfind("}")
            if last_brace_idx > 0:
                valid_part = valid_part[:last_brace_idx + 1]
                # 尝试解析
                try:
                    data = json.loads(valid_part)
                    # 确保结果是字典并包含必要的字段
                    if isinstance(data, dict):
                        result = dict(self.default_data_structure)
                        # 合并有效的字段
                        for key, value in data.items():
                            if key in result:
                                result[key] = value
                        return result
                except:
                    pass
        except Exception as e:
            print(f"修复方法1失败: {e}")
        
        # 方法2: 尝试读取最后一个有效的JSON结构
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # 寻找最后一个有效的JSON结构
            last_brace_pos = content.rfind("}")
            if last_brace_pos > 0:
                valid_part = content[:last_brace_pos + 1]
                # 尝试解析
                try:
                    data = json.loads(valid_part)
                    # 确保结果是字典并包含必要的字段
                    if isinstance(data, dict):
                        result = dict(self.default_data_structure)
                        # 合并有效的字段
                        for key, value in data.items():
                            if key in result:
                                result[key] = value
                        return result
                except Exception:
                    pass
        except Exception as e:
            print(f"修复方法2失败: {e}")
        
        # 如果所有修复方法都失败，返回默认数据结构
        print("无法修复数据文件，使用默认数据结构")
        return dict(self.default_data_structure)
        
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
            
            # 打印调试信息
            
            # 先写入临时文件
            temp_file = f"{self.data_file}.tmp"
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.games_data, f, ensure_ascii=False, indent=2)
                f.flush()  # 确保数据写入磁盘
                
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
            

                
        except Exception as e:
            if not silent:
                print(f"保存数据失败: {str(e)}")
                # 打印详细错误信息便于调试
                import traceback
                traceback.print_exc()
            return False
    
    def update_game(self, app_id: str, database_name: str = None, game_name: Optional[str] = None, 
                   is_unlocked: Optional[bool] = None, auto_save: bool = False, **kwargs) -> None:
        """更新游戏信息，只更新指定的字段
        
        Args:
            app_id: 游戏的AppID（必填）
            database_name: 数据库名称，如果为None则不更新
            game_name: 游戏名称，如果为None则不更新
            is_unlocked: 是否已解锁，如果为None则不更新
            auto_save: 是否自动保存到文件
            **kwargs: 其他自定义字段
        """
        # 确保games字典存在
        if "games" not in self.games_data:
            self.games_data["games"] = {}
            
        # 获取现有游戏数据或创建新的标准游戏数据结构
        game = self.games_data["games"].get(app_id, {
            "app_id": app_id,
            "game_name": "",
            "databases": [],
            "is_unlocked": False,
            "last_updated": datetime.datetime.now().isoformat()
        })
        
        # 确保app_id字段存在（冗余存储，方便查询）
        game["app_id"] = app_id
        
        # 更新数据库名称（如果提供了）
        if database_name is not None:
            databases = game.get("databases", [])
            if database_name and database_name not in databases:
                databases.append(database_name)
                game["databases"] = databases
            
        # 更新游戏名称（如果提供了）
        if game_name is not None and game_name.strip():
            # 打印详细日志用于调试
            old_name = game.get("game_name", "")
            print(f"更新游戏名称 AppID={app_id}: '{old_name}' -> '{game_name}'")
            game["game_name"] = game_name
                
        # 更新解锁状态（如果提供了）
        if is_unlocked is not None:
            game["is_unlocked"] = is_unlocked
            
        # 更新任何其他自定义字段
        for key, value in kwargs.items():
            if value is not None:
                game[key] = value
            
        # 更新最后修改时间
        game["last_updated"] = datetime.datetime.now().isoformat()
        
        # 保存回字典
        self.games_data["games"][app_id] = game
        
        # 如果需要自动保存，则保存到文件
        if auto_save:
            self.save_data()
    
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
            
            # 更新游戏信息，只传递需要更新的字段
            self.update_game(
                app_id=app_id, 
                database_name=database_name,
                auto_save=False
            )
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
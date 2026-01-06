"""
游戏数据库模型 - 轻量级 JSON 数据库
管理游戏信息、depot、manifest、密钥等数据
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field


@dataclass
class Depot:
    """Depot 数据结构"""
    depot_id: str
    manifest_id: str = ""
    decryption_key: str = ""
    size: str = ""
    download: str = ""


@dataclass
class Game:
    """游戏数据结构"""
    app_id: str
    name: str = ""
    schinese_name: str = ""
    type: str = "Game"
    is_free: bool = False
    depots: Dict[str, Depot] = field(default_factory=dict)
    dlc_ids: List[str] = field(default_factory=list)
    repositories: List[str] = field(default_factory=list)
    update_time: str = ""
    is_unlocked: bool = False
    image_url: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = asdict(self)
        result['depots'] = {k: asdict(v) for k, v in self.depots.items()}
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Game':
        """从字典创建"""
        depots = {}
        for depot_id, depot_data in data.get('depots', {}).items():
            if isinstance(depot_data, dict):
                depots[depot_id] = Depot(
                    depot_id=depot_id,
                    manifest_id=depot_data.get('manifest_id', ''),
                    decryption_key=depot_data.get('decryption_key', ''),
                    size=depot_data.get('size', ''),
                    download=depot_data.get('download', '')
                )
        
        return cls(
            app_id=data.get('app_id', ''),
            name=data.get('name', ''),
            schinese_name=data.get('schinese_name', ''),
            type=data.get('type', 'Game'),
            is_free=data.get('is_free', False),
            depots=depots,
            dlc_ids=data.get('dlc_ids', []),
            repositories=data.get('repositories', []),
            update_time=data.get('update_time', ''),
            is_unlocked=data.get('is_unlocked', False),
            image_url=data.get('image_url', '')
        )
    
    @classmethod
    def from_repo_json(cls, json_data: Dict[str, Any], repo_name: str = "") -> 'Game':
        """从仓库 JSON 文件创建游戏对象"""
        app_id = str(json_data.get('appid', ''))
        depots = {}
        
        depot_data = json_data.get('depot', {})
        for key, value in depot_data.items():
            if key == 'branches':
                continue
            if isinstance(value, dict) and 'manifests' in value:
                manifest_info = value.get('manifests', {}).get('public', {})
                depots[key] = Depot(
                    depot_id=key,
                    manifest_id=manifest_info.get('gid', ''),
                    decryption_key=value.get('decryptionkey', ''),
                    size=manifest_info.get('size', ''),
                    download=manifest_info.get('download', '')
                )
        
        return cls(
            app_id=app_id,
            name=json_data.get('name', ''),
            schinese_name=json_data.get('schinese_name', ''),
            type=json_data.get('type', 'Game'),
            is_free=json_data.get('isfreeapp', 0) == 1,
            depots=depots,
            repositories=[repo_name] if repo_name else [],
            update_time=json_data.get('update_time', ''),
            is_unlocked=False
        )


class GamesDatabase:
    """游戏数据库管理类"""
    
    def __init__(self, db_file: str = "data/games_db.json"):
        self.db_file = db_file
        self.games: Dict[str, Game] = {}
        self.last_update = ""
        self._ensure_data_dir()
        self._load()
    
    def _ensure_data_dir(self):
        """确保数据目录存在"""
        Path(self.db_file).parent.mkdir(parents=True, exist_ok=True)
    
    def _load(self):
        """加载数据库"""
        if not os.path.exists(self.db_file):
            return
        
        try:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.last_update = data.get('last_update', '')
            for app_id, game_data in data.get('games', {}).items():
                self.games[app_id] = Game.from_dict(game_data)
        except Exception as e:
            print(f"加载数据库失败: {e}")
    
    def save(self):
        """保存数据库"""
        try:
            self.last_update = datetime.now().isoformat()
            data = {
                'last_update': self.last_update,
                'games': {app_id: game.to_dict() for app_id, game in self.games.items()}
            }
            
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据库失败: {e}")
    
    def add_game(self, game: Game, auto_save: bool = False):
        """添加或更新游戏"""
        existing = self.games.get(game.app_id)
        if existing:
            # 合并仓库列表
            repos = set(existing.repositories) | set(game.repositories)
            game.repositories = list(repos)
            # 保留解锁状态
            game.is_unlocked = existing.is_unlocked
        
        self.games[game.app_id] = game
        if auto_save:
            self.save()
    
    def get_game(self, app_id: str) -> Optional[Game]:
        """获取游戏"""
        return self.games.get(app_id)
    
    def get_all_games(self) -> List[Game]:
        """获取所有游戏"""
        return list(self.games.values())
    
    def set_unlocked(self, app_id: str, unlocked: bool = True):
        """设置解锁状态"""
        if app_id in self.games:
            self.games[app_id].is_unlocked = unlocked
    
    def search(self, keyword: str) -> List[Game]:
        """搜索游戏"""
        keyword = keyword.lower()
        results = []
        for game in self.games.values():
            if (keyword in game.name.lower() or 
                keyword in game.schinese_name.lower() or
                keyword in game.app_id):
                results.append(game)
        return results
    
    def import_from_repo_json(self, json_path: str, repo_name: str = ""):
        """从仓库 JSON 文件导入游戏"""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            game = Game.from_repo_json(data, repo_name)
            self.add_game(game)
            return game
        except Exception as e:
            print(f"导入失败 {json_path}: {e}")
            return None
    
    def get_stats(self) -> Dict[str, int]:
        """获取统计信息"""
        total = len(self.games)
        unlocked = sum(1 for g in self.games.values() if g.is_unlocked)
        free = sum(1 for g in self.games.values() if g.is_free)
        return {
            'total': total,
            'unlocked': unlocked,
            'free': free,
            'locked': total - unlocked - free
        }

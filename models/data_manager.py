import sqlite3
import json
import os
import datetime
import copy
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Set

class DataManager:
    """管理游戏数据的本地存储(Model层) - SQLite 版本"""
    
    def __init__(self, db_file: str = "games_data.db", json_file: str = "games_data.json", config_model=None):
        """初始化数据管理器
        
        Args:
            db_file: SQLite 数据库文件路径
            json_file: 旧的 JSON 数据文件路径（用于迁移）
            config_model: 配置模型，用于获取隐私设置
        """
        self.db_file = db_file
        self.json_file = json_file
        self.config_model = config_model
        
        # 初始化数据库
        self._init_db()
        
        # 如果数据库为空且 JSON 文件存在，执行迁移
        if self._is_db_empty() and os.path.exists(self.json_file):
            print(f"检测到旧数据文件 {self.json_file}，正在迁移至 SQLite...")
            self._migrate_from_json()
            


    def _get_conn(self):
        """获取数据库连接"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        with self._get_conn() as conn:
            # 游戏主表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    app_id TEXT PRIMARY KEY,
                    game_name TEXT,
                    databases TEXT,
                    is_unlocked INTEGER,
                    last_updated TEXT,
                    extra_data TEXT
                )
            """)
            
            # 元数据表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            
            # 初始化最后更新时间
            conn.execute("INSERT OR IGNORE INTO metadata (key, value) VALUES ('last_update', ?)", 
                        (datetime.datetime.now().isoformat(),))
            conn.commit()

    def _is_db_empty(self) -> bool:
        """检查数据库是否为空"""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM games")
            count = cursor.fetchone()[0]
            return count == 0


    def _migrate_from_json(self):
        """从旧的 JSON 文件迁移数据"""
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            games_dict = data.get("games", {})
            last_update = data.get("last_update", datetime.datetime.now().isoformat())
            
            with self._get_conn() as conn:
                for app_id, game_data in games_dict.items():
                    # 根据隐私设置决定迁移哪些数据
                    save_names = self.config_model.get("save_game_names", False) if self.config_model else False
                    save_extra = self.config_model.get("save_extra_data", False) if self.config_model else False
                    
                    game_name = game_data.get("game_name", "") if save_names else ""
                    databases = json.dumps(game_data.get("databases", [])) if save_extra else "[]"
                    is_unlocked = 1 if game_data.get("is_unlocked", False) else 0
                    last_updated = game_data.get("last_updated", datetime.datetime.now().isoformat())
                    
                    extra_data = "{}"
                    if save_extra:
                        extra_data_dict = {k: v for k, v in game_data.items() 
                                         if k not in ["app_id", "game_name", "databases", "is_unlocked", "last_updated"]}
                        extra_data = json.dumps(extra_data_dict)
                    
                    conn.execute("""
                        INSERT OR REPLACE INTO games (app_id, game_name, databases, is_unlocked, last_updated, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (app_id, game_name, databases, is_unlocked, last_updated, extra_data))
                
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_update', ?)", (last_update,))
                conn.commit()
            
            print(f"数据迁移完成，共迁移 {len(games_dict)} 条记录")
            
            # 迁移成功后，将旧文件重命名备份
            backup_name = f"{self.json_file}.migrated.bak"
            if not os.path.exists(backup_name):
                os.rename(self.json_file, backup_name)
                print(f"旧数据文件已重命名为 {backup_name}")
                
        except Exception as e:
            print(f"迁移数据出错: {e}")

    def save_data(self, silent: bool = False) -> bool:
        """保存数据（SQLite 版本中，主要用于更新全局 metadata 的时间戳）"""
        try:
            with self._get_conn() as conn:
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_update', ?)", 
                            (datetime.datetime.now().isoformat(),))
                conn.commit()
            return True
        except Exception as e:
            if not silent:
                print(f"更新元数据失败: {e}")
            return False

    def update_game(self, app_id: str, database_name: str = None, game_name: Optional[str] = None, 
                   is_unlocked: Optional[bool] = None, auto_save: bool = False, **kwargs) -> None:
        """更新游戏信息"""
        try:
            save_names = self.config_model.get("save_game_names", False) if self.config_model else False
            save_extra = self.config_model.get("save_extra_data", False) if self.config_model else False
            
            with self._get_conn() as conn:
                # 1. 获取现有数据
                cursor = conn.execute("SELECT * FROM games WHERE app_id = ?", (app_id,))
                row = cursor.fetchone()
                
                if row:
                    # 更新已有记录
                    current_databases = json.loads(row['databases']) if row['databases'] else []
                    if save_extra and database_name and database_name not in current_databases:
                        current_databases.append(database_name)
                    
                    new_game_name = ""
                    if save_names:
                        new_game_name = game_name if game_name is not None else row['game_name']
                        
                    new_is_unlocked = (1 if is_unlocked else 0) if is_unlocked is not None else row['is_unlocked']
                    new_databases = json.dumps(current_databases) if save_extra else "[]"
                    
                    # 合并 extra_data
                    new_extra_data = "{}"
                    if save_extra:
                        extra_dict = json.loads(row['extra_data']) if row['extra_data'] else {}
                        extra_dict.update(kwargs)
                        new_extra_data = json.dumps(extra_dict)
                else:
                    # 创建新记录
                    new_game_name = game_name if (save_names and game_name is not None) else ""
                    new_is_unlocked = 1 if is_unlocked else 0
                    new_databases = json.dumps([database_name] if (save_extra and database_name) else [])
                    new_extra_data = json.dumps(kwargs if save_extra else {})

                last_updated = datetime.datetime.now().isoformat()
                
                conn.execute("""
                    INSERT OR REPLACE INTO games (app_id, game_name, databases, is_unlocked, last_updated, extra_data)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (app_id, new_game_name, new_databases, new_is_unlocked, last_updated, new_extra_data))
                
                # 更新元数据的时间戳
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_update', ?)", 
                            (last_updated,))
                conn.commit()
        except Exception as e:
            print(f"更新游戏 {app_id} 失败: {e}")

    def get_all_games(self) -> List[Dict[str, Any]]:
        """获取所有游戏信息"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT * FROM games")
                rows = cursor.fetchall()
                
                games = []
                for row in rows:
                    game = {
                        "app_id": row['app_id'],
                        "game_name": row['game_name'],
                        "databases": json.loads(row['databases']) if row['databases'] else [],
                        "is_unlocked": bool(row['is_unlocked']),
                        "last_updated": row['last_updated']
                    }
                    # 合并额外数据
                    if row['extra_data']:
                        extra = json.loads(row['extra_data'])
                        game.update(extra)
                    games.append(game)
                return games
        except Exception as e:
            print(f"查询所有游戏失败: {e}")
            return []

    def get_game(self, app_id: str) -> Optional[Dict[str, Any]]:
        """获取指定AppID的游戏信息"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT * FROM games WHERE app_id = ?", (app_id,))
                row = cursor.fetchone()
                if not row:
                    return None
                
                game = {
                    "app_id": row['app_id'],
                    "game_name": row['game_name'],
                    "databases": json.loads(row['databases']) if row['databases'] else [],
                    "is_unlocked": bool(row['is_unlocked']),
                    "last_updated": row['last_updated']
                }
                if row['extra_data']:
                    game.update(json.loads(row['extra_data']))
                return game
        except Exception as e:
            print(f"查询游戏 {app_id} 失败: {e}")
            return None

    def set_unlock_status(self, app_id: str, is_unlocked: bool, auto_save: bool = False) -> None:
        """设置游戏的解锁状态"""
        try:
            with self._get_conn() as conn:
                last_updated = datetime.datetime.now().isoformat()
                conn.execute(
                    "UPDATE games SET is_unlocked = ?, last_updated = ? WHERE app_id = ?",
                    (1 if is_unlocked else 0, last_updated, app_id)
                )
                conn.commit()
        except sqlite3.Error as e:
            print(f"数据库错误 (set_unlock_status): {e}")

    def batch_set_unlock_status(self, updates: List[Tuple[str, bool]], auto_save: bool = True) -> int:
        """批量设置游戏的解锁状态 (高性能事务)"""
        if not updates:
            return 0
        try:
            with self._get_conn() as conn:
                last_updated = datetime.datetime.now().isoformat()
                # 使用 executemany 进行批量更新
                cursor = conn.executemany(
                    "UPDATE games SET is_unlocked = ?, last_updated = ? WHERE app_id = ?",
                    [(1 if unlocked else 0, last_updated, app_id) for app_id, unlocked in updates]
                )
                
                # 如果是新增状态，上述 UPDATE 可能影响 0 行，但此处我们主要负责更新现有项的状态
                # 如果业务逻辑需要，可以配合 INSERT OR IGNORE
                
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_update', ?)", 
                            (last_updated,))
                conn.commit()
                return cursor.rowcount
        except sqlite3.Error as e:
            print(f"数据库错误 (batch_set_unlock_status): {e}")
            return 0
            
    def batch_add_unlocked_games(self, app_ids: List[str]) -> None:
        """批量添加新发现的已解锁游戏 (高性能事务)"""
        if not app_ids:
            return
        try:
            save_names = self.config_model.get("save_game_names", False) if self.config_model else False
            save_extra = self.config_model.get("save_extra_data", False) if self.config_model else False
            
            with self._get_conn() as conn:
                last_updated = datetime.datetime.now().isoformat()
                for app_id in app_ids:
                    game_name = f"已解锁游戏 {app_id}" if save_names else ""
                    databases = "[]"
                    is_unlocked = 1
                    extra_data = "{}"
                    
                    conn.execute("""
                        INSERT OR IGNORE INTO games (app_id, game_name, databases, is_unlocked, last_updated, extra_data)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (app_id, game_name, databases, is_unlocked, last_updated, extra_data))
                conn.commit()
        except sqlite3.Error as e:
            print(f"数据库错误 (batch_add_unlocked_games): {e}")


    def update_games_from_branches(self, branches: List[Tuple[str, str]], silent: bool = False, auto_save: bool = False) -> None:
        """从分支列表通过事务批量更新游戏数据"""
        try:
            with self._get_conn() as conn:
                last_updated = datetime.datetime.now().isoformat()
                
                # 预先获取现有数据以减少循环内的查询（对于大规模数据，可进一步优化）
                # 这里使用简单的处理方式，SQLite 事务本身已经很快了
                for app_id, branch_name in branches:
                    parts = branch_name.split("/")
                    database_name = parts[0] if len(parts) > 1 else "default"
                    
                    # 检查是否存在
                    cursor = conn.execute("SELECT databases, extra_data FROM games WHERE app_id = ?", (app_id,))
                    row = cursor.fetchone()
                    
                    if row:
                        current_databases = json.loads(row['databases']) if row['databases'] else []
                        if database_name not in current_databases:
                            current_databases.append(database_name)
                        new_databases = json.dumps(current_databases)
                        
                        conn.execute("""
                            UPDATE games SET databases = ?, last_updated = ? WHERE app_id = ?
                        """, (new_databases, last_updated, app_id))
                    else:
                        conn.execute("""
                            INSERT INTO games (app_id, game_name, databases, is_unlocked, last_updated, extra_data)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (app_id, "", json.dumps([database_name]), 0, last_updated, json.dumps({})))
                
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_update', ?)", 
                            (last_updated,))
                conn.commit()
                
            if not silent:
                print(f"批量更新完成，更新了 {len(branches)} 个分支数据")
        except Exception as e:
            print(f"批量从分支更新失败: {e}")

    def get_game_databases(self, app_id: str) -> List[str]:
        """获取游戏的数据库列表"""
        game = self.get_game(app_id)
        return game.get("databases", []) if game else []

    def get_steam_game_names(self, app_ids: List[str]) -> Dict[str, str]:
        """获取游戏名称"""
        game_names = {}
        try:
            with self._get_conn() as conn:
                # 批量查询
                placeholders = ','.join(['?'] * len(app_ids))
                cursor = conn.execute(f"SELECT app_id, game_name FROM games WHERE app_id IN ({placeholders})", app_ids)
                for row in cursor:
                    game_names[row['app_id']] = row['game_name'] if row['game_name'] else f"Game {row['app_id']}"
            return game_names
        except Exception:
            return {app_id: f"Game {app_id}" for app_id in app_ids}

    def get_last_update(self) -> Optional[str]:
        """获取最后更新时间"""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute("SELECT value FROM metadata WHERE key = 'last_update'")
                row = cursor.fetchone()
                return row[0] if row else None
        except:
            return None
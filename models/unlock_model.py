import shutil
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Callable
import aiofiles

# 导入解锁脚本，假设它已经存在于项目根目录
from models import unlock_script


class UnlockModel:
    """游戏解锁功能的模型层"""
    
    def __init__(self, config: Dict[str, str]):
        """初始化解锁模型
        
        Args:
            config: 应用程序配置字典，包含steam_path和manifest_repo_path
        """
        self.config = config
    
    def get_steam_path(self) -> Path:
        """获取Steam安装路径
        
        Returns:
            Steam安装路径的Path对象
        """
        return Path(self.config.get("steam_path", ""))
    
    def get_repo_path(self) -> Path:
        """获取清单仓库路径
        
        Returns:
            清单仓库路径的Path对象
        """
        return Path(self.config.get("manifest_repo_path", ""))
    
    def is_config_valid(self) -> bool:
        """检查配置是否有效
        
        Returns:
            配置是否有效
        """
        steam_path = self.get_steam_path()
        repo_path = self.get_repo_path()
        
        return (
            steam_path.exists() and 
            repo_path.exists() and 
            (repo_path / ".git").exists()
        )
    
    async def check_unlock_status(self, app_id: str) -> bool:
        """检查游戏是否已解锁
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            游戏是否已解锁
        """
        steam_path = self.get_steam_path()
        
        # 检查是否有appid.lua文件，这是判断游戏是否解锁的标志
        stplug_dir = steam_path / "config" / "stplug-in"
        if stplug_dir.exists():
            st_file = stplug_dir / f"{app_id}.lua"
            if st_file.exists():
                return True
            
        # 检查GreenLuma AppList目录中是否有对应的文本文件（作为备选方案）
        applist_dir = steam_path / "AppList"
        if applist_dir.exists():
            for txt_file in applist_dir.glob("*.txt"):
                try:
                    content = txt_file.read_text().strip()
                    if content == app_id:
                        return True
                except Exception:
                    pass
        
        return False
    
    async def check_unlock_status_async(self, app_id: str) -> bool:
        """检查游戏是否已解锁(异步版本)
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            游戏是否已解锁
        """
        return await self.check_unlock_status(app_id)
    
    async def unlock_game(self, app_id: str, database_name: str) -> Tuple[bool, str]:
        """解锁游戏 - 只复制必要文件
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_config_valid():
            return False, "配置无效"
            
        repo_path = self.get_repo_path()
        steam_path = self.get_steam_path()
        
        try:
            # 使用Git检出对应的分支
            # 查找匹配的分支
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return False, "Git操作失败"
                
            # 从输出中找到匹配的分支
            branches = result.stdout.splitlines()
            target_branch = None
            
            for branch in branches:
                branch = branch.strip()
                if app_id in branch:
                    target_branch = branch.replace("*", "").strip()
                    if target_branch.startswith("remotes/"):
                        target_branch = target_branch.split("/", 2)[-1]
                    break
            
            if not target_branch:
                return False, "未找到分支"
                
            # 检出目标分支
            result = subprocess.run(
                ["git", "checkout", target_branch],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return False, "Git检出失败"
                
            # 直接从仓库复制文件到Steam目录
            lua_file = repo_path / f"{app_id}.lua"
            
            # 设置路径
            st_path = steam_path / "config" / "stplug-in"
            st_path.mkdir(exist_ok=True)
            
            depot_cache = steam_path / "config" / "depotcache"
            depot_cache.mkdir(exist_ok=True)
            
            # 复制.lua文件(如果存在)
            if lua_file.exists():
                dst_lua = st_path / f"{app_id}.lua"
                shutil.copy2(str(lua_file), str(dst_lua))
            
            # 复制所有manifest文件
            success = False
            for manifest_file in repo_path.glob("*.manifest"):
                dst_manifest = depot_cache / manifest_file.name
                if not dst_manifest.exists():
                    shutil.copy2(str(manifest_file), str(dst_manifest))
                    success = True
            
            return True, "成功"
                
        except Exception:
            return False, "错误"
    
    async def unlock_game_async(self, app_id: str, database_name: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """解锁游戏(异步版本，带进度回调)
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            progress_callback: 进度回调函数，接收消息和进度百分比
            
        Returns:
            (是否成功, 消息)
        """
        # 报告进度：开始解锁
        if progress_callback:
            progress_callback("开始解锁游戏...", 10)
            
        # 执行解锁
        result = await self.unlock_game(app_id, database_name)
        
        # 报告进度：完成
        if progress_callback:
            progress_callback("解锁操作完成", 100)
            
        return result
    
    async def remove_unlock(self, app_id: str) -> Tuple[bool, str]:
        """移除游戏解锁
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_config_valid():
            return False, "配置无效，请先配置Steam路径和清单仓库路径"
            
        steam_path = self.get_steam_path()
        
        try:
            # 移除SteamTools插件目录中的.lua文件
            st_file = steam_path / "config" / "stplug-in" / f"{app_id}.lua"
            if st_file.exists():
                st_file.unlink()
            
            # 移除GreenLuma AppList目录中的文本文件（作为备选方案）
            applist_dir = steam_path / "AppList"
            if applist_dir.exists():
                for txt_file in applist_dir.glob("*.txt"):
                    try:
                        content = txt_file.read_text().strip()
                        if content == app_id:
                            txt_file.unlink()
                    except Exception:
                        pass
            
            return True, f"游戏 {app_id} 的解锁已移除，请重启Steam"
            
        except Exception as e:
            return False, f"移除解锁时出错: {str(e)}"
            
    async def remove_unlock_async(self, app_id: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """移除游戏解锁(异步版本，带进度回调)
        
        Args:
            app_id: 游戏的AppID
            progress_callback: 进度回调函数，接收消息和进度百分比
            
        Returns:
            (是否成功, 消息)
        """
        # 报告进度：开始移除解锁
        if progress_callback:
            progress_callback("开始移除游戏解锁...", 10)
            
        # 执行移除解锁
        result = await self.remove_unlock(app_id)
        
        # 报告进度：完成
        if progress_callback:
            progress_callback("移除解锁操作完成", 100)
            
        return result
    
    async def scan_unlocked_games(self) -> Dict[str, bool]:
        """扫描所有已解锁的游戏
        
        Returns:
            以AppID为键，解锁状态为值的字典
        """
        unlocked_games = {}
    
        if not self.is_config_valid():
            return unlocked_games
            
        steam_path = self.get_steam_path()
        
        # 扫描SteamTools插件目录中的.lua文件
        plugin_dir = steam_path / "config" / "stplug-in"
        if plugin_dir.exists():
            for st_file in plugin_dir.glob("*.lua"):
                app_id = st_file.stem
                if app_id.isdigit():  # 只处理纯数字的AppID
                    unlocked_games[app_id] = True

        else:
            print(f"警告: 插件目录不存在 - {plugin_dir}")
        
        # 扫描GreenLuma AppList目录中的txt文件
        applist_dir = steam_path / "AppList"
        if applist_dir.exists():
            for txt_file in applist_dir.glob("*.txt"):
                try:
                    async with aiofiles.open(txt_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        app_id = content.strip()
                        if app_id.isdigit():  # 只处理纯数字的AppID
                            unlocked_games[app_id] = True

                except Exception as e:
                    print(f"读取GreenLuma文件 {txt_file} 时出错: {e}")
                    continue
        
        print(f"扫描完成，共发现 {len(unlocked_games)} 个已解锁游戏")
        return unlocked_games 
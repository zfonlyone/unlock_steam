import os
import shutil
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any, Callable
import aiofiles

# 导入解锁脚本，假设它已经存在于项目根目录
import unlock_script

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
        
        # 检查是否有appid.st文件，这是判断游戏是否解锁的标志
        stplug_dir = steam_path / "config" / "stplug-in"
        if stplug_dir.exists():
            st_file = stplug_dir / f"{app_id}.st"
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
        """解锁游戏
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_config_valid():
            return False, "配置无效，请先配置Steam路径和清单仓库路径"
            
        repo_path = self.get_repo_path()
        steam_path = self.get_steam_path()
        
        # 创建临时目录
        temp_dir = repo_path.parent / "steamunlock_temp" / app_id
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # 使用Git检出对应的分支
            branch_pattern = f"*{app_id}*"
            
            # 查找匹配的分支
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return False, f"Git操作失败: {result.stderr}"
                
            # 从输出中找到匹配的分支
            branches = result.stdout.splitlines()
            target_branch = None
            
            for branch in branches:
                branch = branch.strip()
                if app_id in branch:
                    target_branch = branch.replace("*", "").strip()
                    # 如果是远程分支，转换为本地分支
                    if target_branch.startswith("remotes/"):
                        target_branch = target_branch.split("/", 2)[-1]
                    break
            
            if not target_branch:
                return False, f"未找到包含AppID {app_id} 的分支"
                
            # 检出目标分支
            result = subprocess.run(
                ["git", "checkout", target_branch],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return False, f"Git检出分支失败: {result.stderr}"
                
            # 复制清单文件到临时目录
            manifest_files = list(repo_path.glob("*.manifest"))
            key_files = list(repo_path.glob("key.vdf"))
            lua_file = repo_path / f"{app_id}.lua"
            
            if not manifest_files:
                return False, f"在仓库中未找到任何清单文件(*.manifest)"
                
            # 复制文件
            for file in manifest_files:
                shutil.copy2(str(file), str(temp_dir))
                
            for file in key_files:
                shutil.copy2(str(file), str(temp_dir))
                
            # 如果存在appid.lua文件，也复制它
            if lua_file.exists():
                shutil.copy2(str(lua_file), str(temp_dir))
            
            # 根据appid.lua文件是否存在选择解锁方法
            loop = asyncio.get_event_loop()
            
            if lua_file.exists():
                # 使用直接lua解锁方法
                success = await unlock_script.unlock_process_lua(steam_path, temp_dir, app_id)
                if success:
                    return True, f"游戏 {app_id} 使用Lua方法解锁成功，请重启Steam"
                else:
                    return False, "使用Lua方法解锁失败"
            else:
                # 使用原始解锁方法
                depot_data, depot_map = await unlock_script.process_manifest_folder(temp_dir)
                
                if not depot_data:
                    return False, "No depot keys found in the manifest folder"
                    
                # 复制清单到\Steam\config\depotcache
                await unlock_script.copy_manifests_to_steam(temp_dir, steam_path, depot_map)
                
                # 设置解锁工具
                preferred_tool = self.config.get("preferred_unlock_tool", "steamtools")
                
                if preferred_tool == "steamtools":
                    success = await unlock_script.setup_steamtools(depot_data, app_id, depot_map, steam_path)
                else:
                    success = await unlock_script.setup_greenluma(depot_data, steam_path)
                    
                if success:
                    return True, f"游戏 {app_id} 解锁成功，请重启Steam"
                else:
                    return False, f"设置解锁工具失败"
                
        except Exception as e:
            return False, f"解锁过程中出错: {str(e)}"
            
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
            # 移除SteamTools插件目录中的.st文件
            st_file = steam_path / "config" / "stplug-in" / f"{app_id}.st"
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
        
        # 扫描SteamTools插件目录中的.st文件
        plugin_dir = steam_path / "config" / "stplug-in"
        if plugin_dir.exists():
            for st_file in plugin_dir.glob("*.st"):
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
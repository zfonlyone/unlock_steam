import shutil
import subprocess
import asyncio
from pathlib import Path
from typing import Dict, Tuple, Callable, List
import aiofiles
import os
import time

# 导入解锁脚本，假设它已经存在于项目根目录
from models import unlock_script
from models.git_model import GitModel


class UnlockModel:
    """游戏解锁功能的模型层"""
    
    def __init__(self, config: Dict[str, str]):
        """初始化解锁模型
        
        Args:
            config: 应用程序配置字典，包含steam_path和manifest_repo_path
        """
        self.config = config
        # 设置subprocess启动信息，用于隐藏cmd窗口
        self.startupinfo = None
        if os.name == 'nt':  # 仅在Windows系统上设置
            self.startupinfo = subprocess.STARTUPINFO()
            self.startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.startupinfo.wShowWindow = 0  # SW_HIDE
        
        # 创建Git模型
        self.git_model = GitModel(self.config.get("manifest_repo_path", ""))
    
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
    
    async def unlock_game(self, app_id: str, database_name: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """解锁游戏 - 只复制必要文件
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            progress_callback: 可选的进度回调函数
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_config_valid():
            if progress_callback:
                progress_callback("配置无效", 100)
            return False, "配置无效"
            
        repo_path = self.get_repo_path()
        steam_path = self.get_steam_path()
        
        if progress_callback:
            progress_callback(f"正在查找游戏 {app_id} 的分支...", 20)
            
        try:
            # 使用GitModel查找分支，避免直接调用git命令
            print(f"使用GitModel查找游戏 {app_id} 的分支")
            target_branch = self.git_model.find_branch_by_app_id(app_id)
            
            if not target_branch:
                error_msg = f"未找到游戏 {app_id} 的分支"
                print(error_msg)
                if progress_callback:
                    progress_callback(error_msg, 100)
                return False, error_msg
                
            print(f"找到分支: {target_branch}")
            
            if progress_callback:
                progress_callback(f"正在检出分支 {target_branch}...", 40)
                
            # 检出目标分支
            print(f"正在检出分支 {target_branch}")
            success, checkout_msg = self.git_model.checkout_branch(target_branch)
            
            if not success:
                error_msg = f"Git检出失败: {checkout_msg}"
                print(error_msg)
                if progress_callback:
                    progress_callback(error_msg, 100)
                return False, error_msg
                
            print(f"检出分支成功: {checkout_msg}")
            
            if progress_callback:
                progress_callback("正在复制解锁文件...", 60)
                
            # 直接从仓库复制文件到Steam目录
            lua_file = repo_path / f"{app_id}.lua"
            
            # 设置路径
            st_path = steam_path / "config" / "stplug-in"
            st_path.mkdir(exist_ok=True)
            
            depot_cache = steam_path / "config" / "depotcache"
            depot_cache.mkdir(exist_ok=True)
            
            # 复制.lua文件(如果存在)
            lua_copied = False
            if lua_file.exists():
                print(f"复制Lua文件: {lua_file} -> {st_path / f'{app_id}.lua'}")
                dst_lua = st_path / f"{app_id}.lua"
                shutil.copy2(str(lua_file), str(dst_lua))
                lua_copied = True
                if progress_callback:
                    progress_callback("已复制Lua脚本文件", 70)
            else:
                print(f"Lua文件不存在: {lua_file}")
            
            # 复制所有manifest文件
            manifest_copied = False
            manifest_count = 0
            manifest_files = list(repo_path.glob("*.manifest"))
            print(f"找到 {len(manifest_files)} 个manifest文件")
            
            for manifest_file in manifest_files:
                dst_manifest = depot_cache / manifest_file.name
                if not dst_manifest.exists():
                    print(f"复制manifest文件: {manifest_file} -> {dst_manifest}")
                    shutil.copy2(str(manifest_file), str(dst_manifest))
                    manifest_copied = True
                    manifest_count += 1
                else:
                    print(f"manifest文件已存在，跳过: {dst_manifest}")
            
            if progress_callback:
                progress_callback(f"已复制 {manifest_count} 个清单文件", 90)
            
            if not lua_copied and not manifest_copied:
                error_msg = "没有找到需要复制的文件"
                print(error_msg)
                if progress_callback:
                    progress_callback(error_msg, 100)
                return False, error_msg
            
            if progress_callback:
                progress_callback("解锁完成", 100)
                
            return True, f"成功解锁游戏 {app_id}"
                
        except Exception as e:
            error_msg = f"解锁过程错误: {str(e)}"
            print(f"解锁过程出现异常: {error_msg}")
            if progress_callback:
                progress_callback(error_msg, 100)
            return False, error_msg

    async def unlock_game_from_remote(self, app_id: str, repo_url: str = "https://github.com/SteamAutoCracks/ManifestHub",
                                       progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """从远程仓库直接下载并解锁游戏（无需本地克隆，直接下载到 Steam 目录）
        
        Args:
            app_id: 游戏的AppID
            repo_url: 远程仓库 URL
            progress_callback: 可选的进度回调函数
            
        Returns:
            (是否成功, 消息)
        """
        import urllib.request
        import urllib.error
        import json
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        steam_path = self.get_steam_path()
        if not steam_path.exists():
            if progress_callback:
                progress_callback("Steam 路径无效", 100)
            return False, "Steam 路径无效"
        
        try:
            # 解析 GitHub URL
            if "github.com" not in repo_url:
                return False, "目前仅支持 GitHub 仓库"
            
            parts = repo_url.rstrip("/").split("github.com/")
            repo_path = parts[1].rstrip(".git") if len(parts) > 1 else None
            if not repo_path:
                return False, "无法解析 GitHub URL"
            
            # 设置目标路径
            st_path = steam_path / "config" / "stplug-in"
            st_path.mkdir(exist_ok=True)
            
            depot_cache = steam_path / "config" / "depotcache"
            depot_cache.mkdir(exist_ok=True)
            
            if progress_callback:
                progress_callback(f"正在获取分支文件列表 {app_id}...", 10)
            
            # 使用 GitHub API 获取分支文件列表
            api_url = f"https://api.github.com/repos/{repo_path}/contents?ref={app_id}"
            headers = {"User-Agent": "SteamUnlocker/2.0", "Accept": "application/vnd.github.v3+json"}
            
            files_to_download = []  # [(url, dest_path, filename)]
            raw_base_url = f"https://raw.githubusercontent.com/{repo_path}/{app_id}"
            
            try:
                req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    files_info = json.loads(response.read().decode('utf-8'))
                    
                    for file_info in files_info:
                        if file_info.get("type") != "file":
                            continue
                        
                        filename = file_info.get("name", "")
                        download_url = file_info.get("download_url") or f"{raw_base_url}/{filename}"
                        
                        # 收集 Lua 和 manifest 文件
                        if filename.endswith(".lua"):
                            files_to_download.append((download_url, str(st_path / filename), filename))
                        elif filename.endswith(".manifest"):
                            files_to_download.append((download_url, str(depot_cache / filename), filename))
                            
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False, f"分支 {app_id} 不存在"
                elif e.code == 403:
                    # API 速率限制，回退到猜测模式
                    print(f"API 速率限制，使用回退模式")
                    files_to_download.append((f"{raw_base_url}/{app_id}.lua", str(st_path / f"{app_id}.lua"), f"{app_id}.lua"))
                else:
                    return False, f"获取文件列表失败: {e.code}"
            except Exception as e:
                print(f"获取文件列表出错: {e}，使用回退模式")
                files_to_download.append((f"{raw_base_url}/{app_id}.lua", str(st_path / f"{app_id}.lua"), f"{app_id}.lua"))
            
            if not files_to_download:
                return False, f"分支 {app_id} 没有可下载的文件"
            
            if progress_callback:
                progress_callback(f"发现 {len(files_to_download)} 个文件，开始并发下载...", 30)
            
            # 并发下载函数
            def download_file(args):
                url, dest_path, filename = args
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "SteamUnlocker/2.0"})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        content = response.read()
                        with open(dest_path, 'wb') as f:
                            f.write(content)
                        return (True, filename, len(content))
                except Exception as e:
                    return (False, filename, str(e))
            
            # 并发下载所有文件
            lua_downloaded = False
            manifest_count = 0
            max_workers = min(10, len(files_to_download))  # 最多10个并发
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(download_file, args): args for args in files_to_download}
                
                for future in as_completed(futures):
                    success, filename, info = future.result()
                    if success:
                        if filename.endswith(".lua"):
                            lua_downloaded = True
                            print(f"已下载 Lua: {filename} ({info} 字节)")
                        elif filename.endswith(".manifest"):
                            manifest_count += 1
                            print(f"已下载清单: {filename} ({info} 字节)")
                    else:
                        print(f"下载失败: {filename} - {info}")
            
            if progress_callback:
                progress_callback(f"下载完成，处理中...", 80)
            
            # 如果没有 Lua 文件，尝试从 JSON 或 key.vdf 生成
            if not lua_downloaded:
                # 尝试下载 JSON
                json_url = f"{raw_base_url}/{app_id}.json"
                json_content = None
                try:
                    req = urllib.request.Request(json_url, headers={"User-Agent": "SteamUnlocker/2.0"})
                    with urllib.request.urlopen(req, timeout=30) as response:
                        json_content = json.loads(response.read().decode('utf-8'))
                        print(f"已下载 JSON: {app_id}.json")
                except:
                    pass
                
                if json_content:
                    # 从 JSON 生成 Lua
                    lua_lines = [f"addappid({app_id})"]
                    if "depot" in json_content:
                        for depot_id, depot_data in json_content["depot"].items():
                            if depot_id == "branches" or not depot_id.isdigit():
                                continue
                            decrypt_key = depot_data.get("decryptionkey", "")
                            if decrypt_key:
                                lua_lines.append(f'addappid({depot_id},0,"{decrypt_key}")')
                            manifests = depot_data.get("manifests", {})
                            gid = manifests.get("public", {}).get("gid", "")
                            if gid:
                                lua_lines.append(f'setManifestid({depot_id},"{gid}")')
                    
                    if len(lua_lines) > 1:
                        lua_path = st_path / f"{app_id}.lua"
                        with open(str(lua_path), 'w', encoding='utf-8') as f:
                            f.write("\n".join(lua_lines) + "\n")
                        lua_downloaded = True
                        print(f"已从 JSON 生成 Lua: {lua_path}")
                
                # 尝试 key.vdf
                if not lua_downloaded:
                    key_vdf_url = f"{raw_base_url}/key.vdf"
                    try:
                        req = urllib.request.Request(key_vdf_url, headers={"User-Agent": "SteamUnlocker/2.0"})
                        with urllib.request.urlopen(req, timeout=30) as response:
                            key_vdf_content = response.read().decode('utf-8', errors='ignore')
                            
                            import re
                            lua_lines = [f"addappid({app_id})"]
                            matches = re.findall(r'"(\d+)"\s*\{\s*"DecryptionKey"\s*"([a-fA-F0-9]+)"', key_vdf_content)
                            for depot_id, decrypt_key in matches:
                                lua_lines.append(f'addappid({depot_id},0,"{decrypt_key}")')
                            
                            if len(lua_lines) > 1:
                                lua_path = st_path / f"{app_id}.lua"
                                with open(str(lua_path), 'w', encoding='utf-8') as f:
                                    f.write("\n".join(lua_lines) + "\n")
                                lua_downloaded = True
                                print(f"已从 key.vdf 生成 Lua: {lua_path}")
                    except:
                        pass
            
            if not lua_downloaded:
                return False, "无法下载或生成 Lua 文件"
            
            if progress_callback:
                progress_callback("解锁完成", 100)
            
            return True, f"成功解锁 {app_id} (Manifest={manifest_count})"
            
        except Exception as e:
            error_msg = f"远程解锁出错: {str(e)}"
            print(error_msg)
            if progress_callback:
                progress_callback(error_msg, 100)
            return False, error_msg




    async def unlock_game_direct(self, app_id: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """直接解锁游戏，生成基础 Lua 脚本（仅当远程下载失败时使用）
        
        Args:
            app_id: 游戏的AppID
            progress_callback: 可选的进度回调函数
            
        Returns:
            (是否成功, 消息)
        """
        steam_path = self.get_steam_path()
        if not steam_path.exists():
            if progress_callback:
                progress_callback("Steam 路径无效", 100)
            return False, "Steam 路径无效"
            
        try:
            if progress_callback:
                progress_callback("正在生成基础解锁脚本...", 20)
                
            # 创建正确格式的 Lua 脚本
            # 正确格式: addappid(APPID)
            lua_content = f"addappid({app_id})\n"
            
            # 设置路径
            st_path = steam_path / "config" / "stplug-in"
            st_path.mkdir(exist_ok=True)
            
            dst_lua = st_path / f"{app_id}.lua"
            
            # 检查是否已存在（如果已存在且内容正确则跳过）
            if dst_lua.exists():
                try:
                    existing_content = dst_lua.read_text(encoding='utf-8')
                    # 如果文件内容已经是正确格式，跳过
                    if existing_content.strip().startswith("addappid("):
                        if progress_callback:
                            progress_callback("Lua 脚本已存在且格式正确", 100)
                        return True, f"游戏 {app_id} 已有有效的解锁脚本"
                except:
                    pass
            
            # 写入文件（覆盖错误内容）
            if progress_callback:
                progress_callback("正在写入解锁脚本...", 50)
                
            print(f"创建/覆盖 Lua 文件: {dst_lua}")
            with open(dst_lua, "w", encoding="utf-8") as f:
                f.write(lua_content)

                
            if progress_callback:
                progress_callback("解锁脚本已创建", 90)
                
            if progress_callback:
                progress_callback("解锁完成", 100)
                
            return True, f"成功直接解锁游戏 {app_id} (不使用清单文件)"
                
        except Exception as e:
            error_msg = f"直接解锁过程错误: {str(e)}"
            print(f"直接解锁过程出现异常: {error_msg}")
            if progress_callback:
                progress_callback(error_msg, 100)
            return False, error_msg
            
    async def unlock_game_async(self, app_id: str, database_name: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """解锁游戏(异步版本，带进度回调)
        
        根据设置选择解锁源（远程或本地）
        
        Args:
            app_id: 游戏的AppID
            database_name: 数据库名称
            progress_callback: 进度回调函数，接收消息和进度百分比
            
        Returns:
            (是否成功, 消息)
        """
        if progress_callback:
            progress_callback("开始解锁...", 10)
            
        try:
            unlock_source = self.config.get("unlock_source", "remote")
            
            # 如果设置为本地优先，且配置有效
            if unlock_source == "local" and self.is_config_valid():
                print(f"根据设置优先使用本地仓库解锁 {app_id}...")
                result = await self.unlock_game(app_id, database_name, progress_callback)
                if result[0]:
                    return result
                print(f"本地解锁失败: {result[1]}，尝试远程下载...")
            
            # 尝试从远程下载
            result = await self.unlock_game_from_remote(app_id, progress_callback=progress_callback)
            if result[0]:
                return result
            
            # 远程失败时才尝试直接解锁（生成基础 Lua）
            print(f"远程下载失败: {result[1]}")
            if progress_callback:
                progress_callback("远程失败，尝试基础解锁...", 70)
                
            return await self.unlock_game_direct(app_id, progress_callback)
                
        except Exception as e:
            error_msg = f"解锁出错: {str(e)}"
            print(error_msg)
            if progress_callback:
                progress_callback(error_msg, 100)
            return False, error_msg



    
    async def remove_unlock(self, app_id: str, progress_callback: Callable[[str, int], None] = None) -> Tuple[bool, str]:
        """移除游戏解锁
        
        Args:
            app_id: 游戏的AppID
            progress_callback: 可选的进度回调函数
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_config_valid():
            if progress_callback:
                progress_callback("配置无效，请先配置Steam路径和清单仓库路径", 100)
            return False, "配置无效，请先配置Steam路径和清单仓库路径"
            
        steam_path = self.get_steam_path()
        
        try:
            if progress_callback:
                progress_callback(f"正在移除游戏 {app_id} 的解锁...", 20)
                
            # 尝试解析 .lua 文件获取清单 ID 以便后续清理
            manifest_ids = []
            if st_file.exists():
                try:
                    content = st_file.read_text(encoding='utf-8')
                    # 匹配 setManifestid(2087471,"8648147806255524555")
                    matches = re.findall(r'setManifestid\s*\(\d+\s*,\s*["\'](\d+)["\']\)', content)
                    manifest_ids.extend(matches)
                except Exception as e:
                    print(f"解析 .lua 文件出错: {e}")

            lua_removed = False
            if st_file.exists():
                print(f"移除Lua文件: {st_file}")
                st_file.unlink()
                lua_removed = True
                if progress_callback:
                    progress_callback("已移除Lua脚本文件", 50)
            
            # 清理关联的清单文件
            depot_cache = steam_path / "config" / "depotcache"
            if manifest_ids and depot_cache.exists():
                if progress_callback:
                    progress_callback(f"正在清理 {len(manifest_ids)} 个清单文件...", 60)
                for mid in manifest_ids:
                    # 清单文件通常命名为 {manifest_id}.manifest
                    m_file = depot_cache / f"{mid}.manifest"
                    if m_file.exists():
                        print(f"移除清单文件: {m_file}")
                        m_file.unlink()
            
            if progress_callback:
                progress_callback("检查其他解锁文件...", 70)
                
            # 移除GreenLuma AppList目录中的文本文件（作为备选方案）
            applist_dir = steam_path / "AppList"
            txt_removed = False
            if applist_dir.exists():
                for txt_file in applist_dir.glob("*.txt"):
                    try:
                        content = txt_file.read_text().strip()
                        if content == app_id:
                            print(f"移除TXT文件: {txt_file}")
                            txt_file.unlink()
                            txt_removed = True
                    except Exception as e:
                        print(f"读取TXT文件出错: {e}")
            
            if progress_callback:
                progress_callback("移除操作完成", 90)
                
            if not lua_removed and not txt_removed:
                if progress_callback:
                    progress_callback(f"游戏 {app_id} 可能未解锁", 100)
                return True, f"游戏 {app_id} 可能未解锁"
                
            if progress_callback:
                progress_callback(f"游戏 {app_id} 的解锁已移除，请重启Steam", 100)
                
            return True, f"游戏 {app_id} 的解锁已移除，请重启Steam"
            
        except Exception as e:
            error_msg = f"移除解锁时出错: {str(e)}"
            print(f"移除解锁出现异常: {error_msg}")
            if progress_callback:
                progress_callback(error_msg, 100)
            return False, error_msg
            
    async def disable_unlock(self, app_id: str) -> Tuple[bool, str]:
        """禁用游戏解锁 (移动到备份目录)"""
        steam_path = self.get_steam_path()
        plugin_dir = steam_path / "config" / "stplug-in"
        bak_dir = steam_path / "config" / "stplug-in-bak"
        
        src = plugin_dir / f"{app_id}.lua"
        dst = bak_dir / f"{app_id}.lua"
        
        try:
            if not src.exists():
                return False, "该游戏未解锁或脚本不存在"
            
            bak_dir.mkdir(parents=True, exist_ok=True)
            if dst.exists(): dst.unlink()
            shutil.move(str(src), str(dst))
            return True, "已成功禁用解锁"
        except Exception as e:
            return False, f"禁用失败: {str(e)}"

    async def enable_unlock(self, app_id: str) -> Tuple[bool, str]:
        """重新启用游戏解锁"""
        steam_path = self.get_steam_path()
        plugin_dir = steam_path / "config" / "stplug-in"
        bak_dir = steam_path / "config" / "stplug-in-bak"
        
        src = bak_dir / f"{app_id}.lua"
        dst = plugin_dir / f"{app_id}.lua"
        
        try:
            if not src.exists():
                return False, "找不到备份的脚本文件"
            
            plugin_dir.mkdir(parents=True, exist_ok=True)
            if dst.exists(): dst.unlink()
            shutil.move(str(src), str(dst))
            return True, "已重新启用解锁"
        except Exception as e:
            return False, f"启用失败: {str(e)}"

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
        result = await self.remove_unlock(app_id, progress_callback)
            
        return result
    
    async def scan_unlocked_games(self, progress_callback: Callable[[str], None] = None, batch_callback: Callable[[List[str]], None] = None) -> Dict[str, bool]:
        """扫描所有已解锁的游戏
        
        Args:
            progress_callback: 可选的进度信息回调函数
            batch_callback: 可选的结果分批回调函数 [List[app_id]]
            
        Returns:
            以AppID为键，解锁状态为值的字典
        """
        unlocked_games = {}
        batch_size = 1000
        current_batch = []

        def emit_batch():
            if current_batch and batch_callback:
                batch_callback(list(current_batch))
                current_batch.clear()
    
        if not self.get_steam_path().exists():
            return unlocked_games
            
        steam_path = self.get_steam_path()
        
        if progress_callback:
            progress_callback("正在快速扫描 SteamTools 插件目录...")
            
        # 扫描 SteamTools 插件目录中的 .lua 文件
        plugin_dir = steam_path / "config" / "stplug-in"
        if plugin_dir.exists():
            try:
                with os.scandir(str(plugin_dir)) as it:
                    for i, entry in enumerate(it):
                        if entry.is_file() and entry.name.lower().endswith(".lua"):
                            app_id = entry.name[:-4]
                            if app_id.isdigit():
                                unlocked_games[app_id] = True
                                current_batch.append(app_id)
                                if len(current_batch) >= batch_size: emit_batch()
                        
                        if progress_callback and i > 0 and i % 2000 == 0:
                            progress_callback(f"已扫描 SteamTools 目录 {i} 个文件...")
            except Exception as e:
                print(f"扫描 SteamTools 目录异常: {e}")
        # 扫描备份目录 (已禁用的游戏)
        bak_dir = steam_path / "config" / "stplug-in-bak"
        if bak_dir.exists():
            try:
                with os.scandir(str(bak_dir)) as it:
                    for i, entry in enumerate(it):
                        if entry.is_file() and entry.name.lower().endswith(".lua"):
                            app_id = entry.name[:-4]
                            if app_id.isdigit():
                                unlocked_games[app_id] = "disabled"
                                current_batch.append(app_id)
                                if len(current_batch) >= batch_size: emit_batch()
            except Exception as e:
                print(f"扫描备份目录异常: {e}")
        emit_batch()

        if progress_callback:
            progress_callback("正在扫描 GreenLuma AppList 目录...")
        applist_dir = steam_path / "AppList"
        if applist_dir.exists():
            files = list(applist_dir.glob("*.txt"))
            for i, txt_file in enumerate(files):
                try:
                    async with aiofiles.open(txt_file, "r", encoding="utf-8") as f:
                        content = await f.read()
                        app_id = content.strip()
                        if app_id.isdigit():
                            unlocked_games[app_id] = True
                            current_batch.append(app_id)
                            if len(current_batch) >= batch_size: emit_batch()
                    
                    if progress_callback and i % 100 == 0:
                        progress_callback(f"正在扫描 GreenLuma 目录 ({i}/{len(files)})")

                except Exception as e:
                    print(f"读取GreenLuma文件 {txt_file} 时出错: {e}")
                    continue
            emit_batch()
        
        print(f"扫描完成，共发现 {len(unlocked_games)} 个已解锁游戏")
        return unlocked_games
    
    async def batch_unlock_concurrent(
        self,
        app_ids: List[str],
        progress_callback: Callable[[str, int], None] = None,
        app_data: Dict[str, List[str]] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """高并发批量解锁游戏
        
        优先使用 Go 下载器 (最大带宽)，回退到 Python asyncio
        - Go: 20 API并发 + 100 下载并发
        - Python: 10 API并发 + 50 下载并发
        
        Args:
            app_ids: 要解锁的游戏 AppID 列表
            progress_callback: 进度回调函数
            
        Returns:
            {app_id: (success, message)} 字典
        """
        import subprocess
        import json
        
        steam_path = self.get_steam_path()
        if not steam_path.exists():
            return {app_id: (False, "Steam 路径无效") for app_id in app_ids}
        
        # 获取配置
        github_token = self.config.get("github_token", "")
        repos = self.config.get("repositories", [])
        # 更新默认仓库为用户指定的 SteamAutoCracks/ManifestHub
        repo_url = repos[0].get("url", "") if repos else "https://github.com/SteamAutoCracks/ManifestHub"
        
        # 解析仓库路径，确保提取出 'owner/repo'
        repo_path = ""
        if "github.com" in repo_url:
            # 兼容多种格式: https://github.com/owner/repo.git, http://github.com/owner/repo/, owner/repo
            path_part = repo_url.split("github.com/")[-1].strip("/")
            repo_path = path_part.replace(".git", "")
        
        if not repo_path:
            repo_path = "SteamAutoCracks/ManifestHub"
        
        lua_dir = str(steam_path / "config" / "stplug-in")
        manifest_dir = str(steam_path / "config" / "depotcache")
        
        # 确保目录存在
        os.makedirs(lua_dir, exist_ok=True)
        os.makedirs(manifest_dir, exist_ok=True)
        
        # 优先尝试 Go 下载器 (检查多个位置)
        # 1. 与主程序同目录 (打包后)
        # 2. tools/downloader 目录 (开发时)
        import sys
        possible_paths = [
            Path(__file__).parent.parent / "downloader.exe",  # 项目根目录 (开发 & 放置于此)
            Path(sys.executable).parent / "downloader.exe",  # 打包后同目录
            Path(__file__).parent.parent / "tools" / "downloader" / "downloader.exe",  # 源码目录
        ]
        
        go_binary = None
        for p in possible_paths:
            if p.exists():
                go_binary = p
                break
        
        if go_binary:
            print(f"找到 Go 下载器: {go_binary}")
            if progress_callback:
                progress_callback(f"初始化 Go 下载器... ({go_binary.name})", 2)
                progress_callback(f"模式: {'一键解锁' if len(app_ids) > 1 else '精准解锁'} ({len(app_ids)} 个游戏)", 5)
                progress_callback(f"仓库: {repo_path}", 6)
            
            try:
                # 准备配置
                config_dict = {
                    "token": github_token,
                    "repo": repo_path,
                    "app_ids": app_ids,
                    "app_data": app_data or {},
                    "lua_dir": lua_dir,
                    "manifest_dir": manifest_dir,
                    "direct_mode": True
                }
                
                import tempfile
                import os
                
                # 使用临时文件传递配置，彻底解决 Windows Stdin 管道容量限制问题
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
                    json.dump(config_dict, tmp)
                    temp_config_path = tmp.name
                
                try:
                    # 调用 Go 下载器
                    import time
                    start_time = time.time()
                    
                    process = subprocess.Popen(
                        [str(go_binary), "-config", temp_config_path],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        startupinfo=self.startupinfo,
                        text=False
                    )
                    
                    # 实时读取输出
                    last_json_line = ""
                    results = {}
                    api_remaining = 5000
                    
                    while True:
                        line = process.stdout.readline()
                        if not line and process.poll() is not None:
                            break
                        
                        line_str = line.decode('utf-8', errors='ignore').strip()
                        if not line_str:
                            continue
                            
                        # 尝试解析 JSON 结果
                        if line_str.startswith('{') and '"results"' in line_str:
                            last_json_line = line_str
                            continue
                        
                        # 反馈给 UI
                        if progress_callback:
                            msg = line_str
                            if "[DOWNLOAD_SUCCESS]" in line_str:
                                msg = "✅ 成功: " + line_str.split("]")[-1].strip()
                            elif "[DOWNLOAD_FAIL]" in line_str:
                                msg = "❌ 失败: " + line_str.split("]")[-1].strip()
                            elif "[PROGRESS]" in line_str:
                                # [PROGRESS] 100/500 -> 提取百分比
                                try:
                                    p_str = line_str.split("]")[-1].strip()
                                    curr, total = map(int, p_str.split("/"))
                                    percent = int(curr / total * 100)
                                    progress_callback(f"批量进度: {p_str}", percent)
                                    continue
                                except: pass
                                
                            progress_callback(msg, -1)
                    
                    process.wait()
                    
                    if process.returncode == 0 and last_json_line:
                        result_json = json.loads(last_json_line)
                        for r in result_json.get("results", []):
                            aid = r.get("app_id", "")
                            err = r.get("error", "")
                            lua = r.get("lua", 0)
                            mf = r.get("manifest", 0)
                            if err: results[aid] = (False, err)
                            elif lua > 0: results[aid] = (True, f"成功 (Lua={lua}, Manifest={mf})")
                            else: results[aid] = (False, "缺失 Lua")
                        
                        api_remaining = result_json.get("api_remaining", api_remaining)
                        
                        # --- Python 异步补漏 ---
                        missing_ids = [aid for aid, (succ, msg) in results.items() if not succ]
                        if missing_ids:
                            if progress_callback: progress_callback(f"正在补全 {len(missing_ids)} 个缺失项...", -1)
                            sem = asyncio.Semaphore(20)
                            async def repair(aid):
                                async with sem:
                                    return await self.unlock_game_async(aid, "", None)
                            
                            repair_tasks = [repair(aid) for aid in missing_ids]
                            repair_res = await asyncio.gather(*repair_tasks)
                            for aid, (succ, msg) in zip(missing_ids, repair_res):
                                if succ: results[aid] = (True, f"已补齐: {msg}")
                                
                        if progress_callback:
                            succ_cnt = sum(1 for s, _ in results.values() if s)
                            progress_callback(f"解锁完成! 成功: {succ_cnt}/{len(app_ids)}", 100)
                        
                        return results
                    else:
                        print(f"Go 下载器未返回预期结果 (退出码 {process.returncode})")
                        
                finally:
                    # 确保清理临时文件
                    if os.path.exists(temp_config_path):
                        try: os.remove(temp_config_path)
                        except: pass
            except Exception as e:
                print(f"Go 下载器执行监控异常: {e}")
                import traceback
                traceback.print_exc()
        
        # 回退到 Python asyncio
        if progress_callback:
            progress_callback(f"使用 Python 支持方案 ({len(app_ids)} 个游戏, 30并发)...", 5)
        
        try:
            # 引入加强版本地解析/下载器
            import sys
            from tools import downloader as python_downloader
            
            downloader = python_downloader.BatchDownloader(
                token=github_token,
                repo=repo_path,
                lua_dir=lua_dir,
                manifest_dir=manifest_dir,
                api_concurrency=10,
                download_concurrency=30  # 降低并发保护磁盘 IO
            )
            
            batch_result = await downloader.download_batch(app_ids)
            
            results = {}
            for r in batch_result.results:
                if r.error:
                    results[r.app_id] = (False, r.error)
                elif r.lua_count > 0:
                    results[r.app_id] = (True, f"成功 (Lua={r.lua_count}, Manifest={r.manifest_count})")
                else:
                    # 自动生成基础 Lua 兜底
                    succ, msg = await self.unlock_game_direct(r.app_id)
                    results[r.app_id] = (succ, msg if succ else "未找到 Lua 且生成失败")
            
            if progress_callback:
                success_count = sum(1 for s, _ in results.values() if s)
                progress_callback(
                    f"处理完成! 成功: {success_count}/{len(app_ids)}, 耗时: {batch_result.total_time:.1f}秒",
                    100
                )
            
            return results
            
        except Exception as e:
            # 最终回退到逐个解锁
            if progress_callback:
                progress_callback(f"并发模块异常，使用安全模式: {e}", 10)
            results = {}
            for i, app_id in enumerate(app_ids):
                result = await self.unlock_game_async(app_id, "", progress_callback)
                results[app_id] = result
                if progress_callback:
                    progress_callback(f"进度: {i+1}/{len(app_ids)}", int((i+1) / len(app_ids) * 100))
            return results
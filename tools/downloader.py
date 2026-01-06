"""
Steam Unlocker - 高并发下载器 (Python版)
使用 asyncio + aiohttp 实现高性能并发下载

特性:
- GitHub API 获取分支文件列表 (消耗 API 配额)
- raw.githubusercontent.com 下载文件 (不消耗配额)
- asyncio 高并发下载
- 内置速率限制，安全使用 API 配额
- 支持 GitHub Token 认证

用法:
  python downloader.py --token=TOKEN --repo=USER/REPO --ids=123,456,789 --lua=PATH --manifest=PATH
  或在代码中直接调用 BatchDownloader 类
"""
import asyncio
import aiohttp
import json
import os
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from asyncio import Semaphore


@dataclass
class DownloadResult:
    """单个游戏的下载结果"""
    app_id: str
    lua_count: int = 0
    manifest_count: int = 0
    error: str = ""


@dataclass
class BatchResult:
    """批量下载结果"""
    success: bool = True
    results: List[DownloadResult] = field(default_factory=list)
    api_remaining: int = 5000
    total_time: float = 0.0


class BatchDownloader:
    """高并发批量下载器"""
    
    def __init__(
        self,
        token: str = "",
        repo: str = "",
        lua_dir: str = "",
        manifest_dir: str = "",
        api_concurrency: int = 10,      # API 请求并发数
        download_concurrency: int = 50,  # 下载并发数
    ):
        self.token = token
        self.repo = repo
        self.lua_dir = Path(lua_dir) if lua_dir else None
        self.manifest_dir = Path(manifest_dir) if manifest_dir else None
        self.api_concurrency = api_concurrency
        self.download_concurrency = download_concurrency
        self.api_remaining = 5000
        
        # 创建目录
        if self.lua_dir:
            self.lua_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_dir:
            self.manifest_dir.mkdir(parents=True, exist_ok=True)
    
    async def download_batch(self, app_ids: List[str]) -> BatchResult:
        """批量下载多个游戏"""
        start_time = time.time()
        result = BatchResult()
        
        # 创建信号量限制并发
        api_sem = Semaphore(self.api_concurrency)
        download_sem = Semaphore(self.download_concurrency)
        
        # 创建 HTTP 会话
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=50)
        timeout = aiohttp.ClientTimeout(total=60)
        
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            # 并发处理所有游戏
            tasks = [
                self._process_app(session, app_id, api_sem, download_sem)
                for app_id in app_ids
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for r in results:
                if isinstance(r, Exception):
                    result.results.append(DownloadResult(
                        app_id="unknown",
                        error=str(r)
                    ))
                else:
                    result.results.append(r)
        
        result.api_remaining = self.api_remaining
        result.total_time = time.time() - start_time
        return result
    
    async def _process_app(
        self,
        session: aiohttp.ClientSession,
        app_id: str,
        api_sem: Semaphore,
        download_sem: Semaphore
    ) -> DownloadResult:
        """处理单个游戏"""
        result = DownloadResult(app_id=app_id)
        
        try:
            # 获取 API 信号量
            async with api_sem:
                files = await self._get_files_from_api(session, app_id)
            
            if not files:
                result.error = "无法获取文件列表"
                return result
            
            # 收集下载任务
            download_tasks = []
            raw_base_url = f"https://raw.githubusercontent.com/{self.repo}/{app_id}"
            
            for file_info in files:
                if file_info.get("type") != "file":
                    continue
                
                filename = file_info.get("name", "")
                download_url = file_info.get("download_url") or f"{raw_base_url}/{filename}"
                
                if filename.endswith(".lua") and self.lua_dir:
                    dest_path = self.lua_dir / filename
                    download_tasks.append((download_url, dest_path, True))
                elif filename.endswith(".manifest") and self.manifest_dir:
                    dest_path = self.manifest_dir / filename
                    download_tasks.append((download_url, dest_path, False))
            
            # 并发下载所有文件
            lua_count = 0
            manifest_count = 0
            
            async def download_one(url: str, path: Path, is_lua: bool) -> Tuple[bool, bool]:
                async with download_sem:
                    success = await self._download_file(session, url, path)
                    return success, is_lua
            
            download_results = await asyncio.gather(*[
                download_one(url, path, is_lua)
                for url, path, is_lua in download_tasks
            ], return_exceptions=True)
            
            for r in download_results:
                if isinstance(r, tuple):
                    success, is_lua = r
                    if success:
                        if is_lua:
                            lua_count += 1
                        else:
                            manifest_count += 1
            
            result.lua_count = lua_count
            result.manifest_count = manifest_count
            
        except Exception as e:
            result.error = str(e)
        
        return result
    
    async def _get_files_from_api(
        self,
        session: aiohttp.ClientSession,
        branch: str
    ) -> Optional[List[Dict]]:
        """从 GitHub API 获取分支文件列表"""
        url = f"https://api.github.com/repos/{self.repo}/contents?ref={branch}"
        
        headers = {
            "User-Agent": "SteamUnlocker/2.0",
            "Accept": "application/vnd.github.v3+json"
        }
        
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        try:
            async with session.get(url, headers=headers) as response:
                # 更新 API 剩余配额
                remaining = response.headers.get("X-RateLimit-Remaining")
                if remaining:
                    self.api_remaining = int(remaining)
                
                if response.status == 404:
                    return None
                if response.status == 403:
                    # 速率限制
                    return None
                if response.status != 200:
                    return None
                
                return await response.json()
        except Exception:
            return None
    
    async def _download_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        dest_path: Path
    ) -> bool:
        """下载单个文件"""
        headers = {"User-Agent": "SteamUnlocker/2.0"}
        
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    return False
                
                content = await response.read()
                
                # 写入文件
                with open(dest_path, 'wb') as f:
                    f.write(content)
                
                return True
        except Exception:
            return False


async def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description="Steam Unlocker 高并发下载器")
    parser.add_argument("--token", default="", help="GitHub Token")
    parser.add_argument("--repo", required=True, help="GitHub 仓库 (user/repo)")
    parser.add_argument("--ids", required=True, help="App IDs (逗号分隔)")
    parser.add_argument("--lua", default="", help="Lua 文件保存目录")
    parser.add_argument("--manifest", default="", help="Manifest 文件保存目录")
    parser.add_argument("--api-concurrency", type=int, default=10, help="API 并发数")
    parser.add_argument("--download-concurrency", type=int, default=50, help="下载并发数")
    
    args = parser.parse_args()
    
    app_ids = [id.strip() for id in args.ids.split(",") if id.strip()]
    
    downloader = BatchDownloader(
        token=args.token,
        repo=args.repo,
        lua_dir=args.lua,
        manifest_dir=args.manifest,
        api_concurrency=args.api_concurrency,
        download_concurrency=args.download_concurrency
    )
    
    result = await downloader.download_batch(app_ids)
    
    # 输出 JSON 结果
    output = {
        "success": result.success,
        "results": [
            {
                "app_id": r.app_id,
                "lua": r.lua_count,
                "manifest": r.manifest_count,
                "error": r.error
            }
            for r in result.results
        ],
        "api_remaining": result.api_remaining,
        "total_time_seconds": result.total_time
    }
    
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    # Windows 需要设置事件循环策略
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())

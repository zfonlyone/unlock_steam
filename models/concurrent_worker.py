"""
并发工作器 - 使用 Python concurrent.futures
替代 Go 实现的高性能并发处理
"""
import os
import re
import json
import requests
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional, Callable, Any
from pathlib import Path
from functools import partial
import time


class ConcurrentWorker:
    """并发工作器"""
    
    def __init__(self, max_workers: int = None):
        """初始化
        
        Args:
            max_workers: 最大工作线程数，默认为 CPU 核心数
        """
        self.max_workers = max_workers or min(32, (os.cpu_count() or 1) + 4)
    
    def fetch_all_branches(self, repo_path: str) -> List[Tuple[str, str]]:
        """并发获取仓库中所有分支的 AppID
        
        Args:
            repo_path: 仓库路径
            
        Returns:
            [(app_id, branch_name), ...]
        """
        import subprocess
        
        # 获取所有分支
        try:
            result = subprocess.run(
                ['git', 'branch', '-a'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return []
            
            branches = []
            for line in result.stdout.splitlines():
                branch = line.strip().replace('*', '').strip()
                if branch and 'HEAD' not in branch:
                    # 从分支名提取 AppID
                    match = re.search(r'(\d+)', branch)
                    if match:
                        app_id = match.group(1)
                        branches.append((app_id, branch))
            
            return branches
        except Exception as e:
            print(f"获取分支失败: {e}")
            return []
    
    def fetch_game_names_batch(self, app_ids: List[str], batch_size: int = 50) -> Dict[str, str]:
        """批量获取游戏名称 (Steam API)
        
        Args:
            app_ids: AppID 列表
            batch_size: 每批次数量
            
        Returns:
            {app_id: game_name}
        """
        results = {}
        
        def fetch_single(app_id: str) -> Tuple[str, str]:
            try:
                url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&cc=cn&l=schinese"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data.get(app_id, {}).get('success'):
                        name = data[app_id]['data'].get('name', '')
                        return app_id, name
            except:
                pass
            return app_id, ""
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch_single, app_id): app_id for app_id in app_ids}
            
            for future in as_completed(futures):
                try:
                    app_id, name = future.result()
                    if name:
                        results[app_id] = name
                except:
                    pass
        
        return results
    
    def fetch_game_images_batch(self, app_ids: List[str]) -> Dict[str, str]:
        """批量获取游戏封面图 URL
        
        Args:
            app_ids: AppID 列表
            
        Returns:
            {app_id: image_url}
        """
        # Steam 封面图 URL 格式
        # https://cdn.akamai.steamstatic.com/steam/apps/{appid}/header.jpg
        results = {}
        for app_id in app_ids:
            results[app_id] = f"https://cdn.akamai.steamstatic.com/steam/apps/{app_id}/header.jpg"
        return results
    
    def scan_repo_json_files(self, repo_path: str, branch: str = None) -> List[str]:
        """扫描仓库中的所有 JSON 文件
        
        Args:
            repo_path: 仓库路径
            branch: 分支名（可选，如果指定则先 checkout）
            
        Returns:
            JSON 文件路径列表
        """
        import subprocess
        
        if branch:
            try:
                # 处理远程分支
                if branch.startswith('remotes/'):
                    local_branch = branch.split('/')[-1]
                    subprocess.run(
                        ['git', 'checkout', '-b', local_branch, branch],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=10
                    )
                else:
                    subprocess.run(
                        ['git', 'checkout', branch],
                        cwd=repo_path,
                        capture_output=True,
                        timeout=10
                    )
            except:
                pass
        
        json_files = []
        for file in Path(repo_path).glob('*.json'):
            if file.stem.isdigit():  # 只要数字命名的 JSON
                json_files.append(str(file))
        
        return json_files
    
    def process_files_parallel(self, files: List[str], processor: Callable, 
                                use_process: bool = False) -> List[Any]:
        """并行处理文件
        
        Args:
            files: 文件路径列表
            processor: 处理函数
            use_process: 是否使用进程池（CPU 密集型任务）
            
        Returns:
            处理结果列表
        """
        executor_class = ProcessPoolExecutor if use_process else ThreadPoolExecutor
        results = []
        
        with executor_class(max_workers=self.max_workers) as executor:
            futures = {executor.submit(processor, f): f for f in files}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    print(f"处理文件失败: {futures[future]}: {e}")
        
        return results
    
    def check_lua_files_parallel(self, lua_dir: str) -> List[Dict]:
        """并行检查 Lua 文件合法性
        
        Args:
            lua_dir: Lua 文件目录
            
        Returns:
            问题文件列表
        """
        addappid_pattern = re.compile(r'addappid\s*\(([^)]*)\)')
        setmanifest_pattern = re.compile(r'setManifestid\s*\(([^)]*)\)')
        allowed_pattern = re.compile(r'^[a-zA-Z0-9,\s"\']+$')
        
        def check_file(file_path: str) -> Optional[Dict]:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                try:
                    with open(file_path, 'r', encoding='gbk') as f:
                        content = f.read()
                except:
                    return None
            except:
                return None
            
            issues = []
            
            for pattern, name in [(addappid_pattern, 'addappid'), (setmanifest_pattern, 'setManifestid')]:
                for match in pattern.finditer(content):
                    params = match.group(1)
                    if not allowed_pattern.match(params):
                        illegal = [c for c in params if not re.match(r'[a-zA-Z0-9,\s"\']', c)]
                        issues.append({
                            'function': name,
                            'illegal_chars': list(set(illegal)),
                            'content': params[:50]
                        })
            
            if issues:
                return {
                    'file': os.path.basename(file_path),
                    'path': file_path,
                    'issues': issues
                }
            return None
        
        lua_files = list(Path(lua_dir).glob('*.lua'))
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(check_file, str(f)): f for f in lua_files}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                except:
                    pass
        
        return results


# 全局实例
_worker: Optional[ConcurrentWorker] = None


def get_worker(max_workers: int = None) -> ConcurrentWorker:
    """获取并发工作器实例"""
    global _worker
    if _worker is None:
        _worker = ConcurrentWorker(max_workers)
    return _worker

import os
import json
import time
import subprocess
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

class GitModel:
    """Git操作相关的模型层"""
    
    def __init__(self, repo_path: str, cache_file: str = "branch_cache.json"):
        """初始化Git模型
        
        Args:
            repo_path: Git仓库路径
            cache_file: 分支缓存文件路径
        """
        # 标准化仓库路径
        self.repo_path = os.path.normpath(repo_path) if repo_path else ""
        self.cache_file = cache_file
    
    def is_valid_repo(self) -> bool:
        """检查是否是有效的Git仓库
        
        Returns:
            是否是有效的Git仓库
        """
        if not self.repo_path:
            return False
            
        # 使用标准化路径检查.git目录
        git_dir = os.path.join(self.repo_path, ".git")
        return os.path.exists(git_dir)
    
    def _load_cache(self) -> Dict[str, Any]:
        """加载缓存数据
        
        Returns:
            缓存数据字典
        """
        if not os.path.exists(self.cache_file):
            return {"branches": [], "last_position": 0, "last_update": ""}
            
        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"branches": [], "last_position": 0, "last_update": ""}
    
    def _save_cache(self, cache_data: Dict[str, Any]) -> None:
        """保存缓存数据
        
        Args:
            cache_data: 缓存数据字典
        """
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
        except:
            pass
    
    def fetch_branches(self, use_cache: bool = True, batch_size: int = 100) -> List[Tuple[str, str]]:
        """获取仓库中的分支列表
        
        Args:
            use_cache: 是否使用缓存
            batch_size: 批处理大小，设置很大的值将返回全部分支
            
        Returns:
            分支列表，每个元素为(app_id, branch_name)的元组
        """
        if not self.is_valid_repo():
            return []
            
        # 如果使用缓存且缓存存在
        cache_data = self._load_cache()
        all_branches = cache_data.get("branches", [])
        last_position = cache_data.get("last_position", 0)
        
        if use_cache and all_branches and last_position < len(all_branches):
            # 分批处理未处理的分支
            end_position = min(last_position + batch_size, len(all_branches))
            branches_to_process = all_branches[last_position:end_position]
            
            # 更新缓存中的处理位置
            cache_data["last_position"] = end_position
            self._save_cache(cache_data)
            
            return branches_to_process
            
        # 如果不使用缓存或缓存不存在，则从仓库获取分支
        try:
            # 获取本地分支
            local_branches = []
            result = subprocess.run(
                ["git", "branch", "--list"], 
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.splitlines():
                    branch = line.strip().replace("*", "").strip()
                    if branch:
                        # 尝试从分支名提取AppID
                        match = re.search(r'(\d+)', branch)
                        if match:
                            app_id = match.group(1)
                            local_branches.append((app_id, branch))
            
            # 获取远程分支
            remote_branches = []
            result = subprocess.run(
                ["git", "branch", "-r"], 
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.splitlines():
                    remote_branch = line.strip()
                    if remote_branch and "HEAD" not in remote_branch:  # 排除HEAD引用
                        # 尝试从分支名提取AppID
                        match = re.search(r'(\d+)', remote_branch)
                        if match:
                            app_id = match.group(1)
                            remote_branches.append((app_id, remote_branch))
            
            # 合并分支列表
            all_branches = local_branches + remote_branches
            
            # 更新缓存
            cache_data = {
                "branches": all_branches,
                "last_position": len(all_branches),  # 修改这里，将处理位置设为分支总数，表示已全部处理
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._save_cache(cache_data)
            
            # 返回全部分支而不是第一批
            return all_branches
                
        except Exception as e:
            print(f"获取分支失败: {e}")
            return []
    
    def checkout_branch(self, branch_name: str) -> Tuple[bool, str]:
        """检出指定分支
        
        Args:
            branch_name: 分支名称
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_valid_repo():
            return False, "无效的Git仓库"
            
        try:
            result = subprocess.run(
                ["git", "checkout", branch_name],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode == 0:
                return True, f"成功检出分支: {branch_name}"
            else:
                return False, f"检出分支失败: {result.stderr}"
                
        except Exception as e:
            return False, f"检出分支时出错: {str(e)}"
    
    def find_branch_by_app_id(self, app_id: str) -> Optional[str]:
        """根据AppID查找分支
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            分支名称，如果不存在则返回None
        """
        try:
            result = subprocess.run(
                ["git", "branch", "-a"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                return None
                
            branches = result.stdout.splitlines()
            for branch in branches:
                branch = branch.strip().replace("*", "").strip()
                if app_id in branch:
                    # 如果是远程分支，转换为本地分支
                    if branch.startswith("remotes/"):
                        branch = branch.split("/", 2)[-1]
                    return branch
                    
            return None
            
        except Exception:
            return None 
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
        # 设置subprocess启动信息，用于隐藏cmd窗口
        self.startupinfo = None
        if os.name == 'nt':  # 仅在Windows系统上设置
            self.startupinfo = subprocess.STARTUPINFO()
            self.startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            self.startupinfo.wShowWindow = 0  # SW_HIDE
    
    def is_valid_repo(self) -> bool:
        """检查是否是有效的Git仓库
        
        Returns:
            是否是有效的Git仓库
        """
        if not self.repo_path:
            return False
            
        # 使用标准化路径检查.git目录
        git_dir = os.path.join(self.repo_path, ".git")
        if not os.path.exists(git_dir):
            return False
            
        # 检查 git 命令是否可用
        try:
            subprocess.run(["git", "--version"], capture_output=True, startupinfo=self.startupinfo)
            return True
        except:
            print("错误: 系统未找到 git 命令，请确保已安装 Git 并添加到环境变量")
            return False
    
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

    def clone(self, url: str) -> Tuple[bool, str]:
        """克隆远程仓库到本地路径
        
        Args:
            url: 远程仓库 URL
            
        Returns:
            (是否成功, 消息)
        """
        if not self.repo_path:
            return False, "未设置目标路径"
            
        if os.path.exists(self.repo_path) and os.path.exists(os.path.join(self.repo_path, ".git")):
            return True, "仓库已存在"
            
        try:
            # 确保父目录存在
            os.makedirs(os.path.dirname(self.repo_path), exist_ok=True)
            
            print(f"正在克隆仓库 {url} 到 {self.repo_path}...")
            # 使用 --bare 可能更轻量，但这里我们需要常规仓库以便后续操作更简单
            # 对于 ManifestHub 这种大仓，full clone 确实会比较慢
            result = subprocess.run(
                ["git", "clone", "--filter=blob:none", url, self.repo_path], 
                capture_output=True,
                text=True,
                check=False,
                startupinfo=self.startupinfo,
                timeout=600 # 10分钟超时
            )
            
            if result.returncode == 0:
                return True, "仓库克隆成功"
            else:
                error_msg = f"克隆失败: {result.stderr}"
                print(error_msg)
                return False, error_msg
        except Exception as e:
            return False, f"执行 git clone 时出错: {str(e)}"

    def fetch_remote_branches(self, url: str) -> List[Tuple[str, str]]:
        """直接从远程 URL 获取所有分支列表（无需本地克隆）
        
        Args:
            url: 远程仓库 URL (例如 https://github.com/user/repo)
            
        Returns:
            [(app_id, branch_name), ...] 列表
        """
        try:
            print(f"正在从远程获取分支列表: {url}...")
            
            # git ls-remote --heads 只列出分支（不包括标签等）
            result = subprocess.run(
                ["git", "ls-remote", "--heads", url],
                capture_output=True,
                text=True,
                check=False,
                encoding='utf-8',
                errors='ignore',
                startupinfo=self.startupinfo,
                timeout=120  # 2分钟超时
            )
            
            if result.returncode != 0:
                print(f"git ls-remote 失败: {result.stderr}")
                return []
            
            lines = result.stdout.splitlines()
            print(f"远程仓库返回了 {len(lines)} 个分支引用")
            
            if not lines:
                return []
            
            extracted_branches = []
            seen_appids = set()
            
            for line in lines:
                # 格式: <sha>\trefs/heads/<branch_name>
                parts = line.split('\t')
                if len(parts) != 2:
                    continue
                    
                ref = parts[1]
                # 提取分支名：refs/heads/12345 -> 12345
                if ref.startswith("refs/heads/"):
                    branch_name = ref[len("refs/heads/"):]
                else:
                    continue
                
                # 只接受纯数字分支名（即 AppID）
                if branch_name.isdigit():
                    app_id = branch_name
                    if app_id not in seen_appids:
                        extracted_branches.append((app_id, branch_name))
                        seen_appids.add(app_id)
                # 忽略非数字分支如 main, master, feature-xxx 等
            
            print(f"从远程成功筛选出 {len(extracted_branches)} 个有效游戏分支（仅纯数字 AppID）")
            
            if extracted_branches:
                samples = ", ".join([f"{aid}" for aid, _ in extracted_branches[:5]])
                print(f"样例 AppID: {samples}...")
            
            return extracted_branches
            
        except subprocess.TimeoutExpired:
            print(f"git ls-remote 超时 (120秒)")
            return []
        except Exception as e:
            print(f"获取远程分支时出错: {str(e)}")
            return []


    def sync_remote(self) -> Tuple[bool, str]:
        """同步远程仓库 (git fetch --all)"""
        if not self.is_valid_repo():
            return False, "无效的Git仓库路径"
            
        try:
            print(f"正在同步远程库: {self.repo_path}")
            # 对于 62k 分支的大仓，增加超时到 300 秒
            result = subprocess.run(
                ["git", "fetch", "--all", "--prune"], 
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                startupinfo=self.startupinfo,
                timeout=300 
            )
            
            if result.returncode == 0:
                return True, "远程库同步成功"
            else:
                error_msg = f"同步失败: {result.stderr}"
                print(error_msg)
                return False, error_msg
        except subprocess.TimeoutExpired:
            return False, "同步超时 (300秒)，建议在命令行手动执行 git fetch"
        except Exception as e:
            return False, f"执行git fetch时出错: {str(e)}"

    def fetch_branches(self, use_cache: bool = True, batch_size: int = 100, sync: bool = False) -> List[Tuple[str, str]]:
        """获取仓库中的所有分支列表（针对大仓优化）"""
        if not self.is_valid_repo():
            print(f"无效的仓库路径: {self.repo_path}")
            return []

        if sync:
            success, msg = self.sync_remote()
            if not success:
                print(f"同步提示: {msg}")
            
        # 缓存逻辑保持不变
        cache_data = self._load_cache()
        all_branches_cache = cache_data.get("branches", [])
        last_position = cache_data.get("last_position", 0)
        
        if use_cache and all_branches_cache and last_position < len(all_branches_cache):
            end_position = min(last_position + batch_size, len(all_branches_cache))
            branches_to_process = all_branches_cache[last_position:end_position]
            result_branches = [(b["app_id"], b["branch_name"]) for b in branches_to_process]
            cache_data["last_position"] = end_position
            self._save_cache(cache_data)
            return result_branches
            
        try:
            # 针对 62k 分支优化：使用 for-each-ref 代替 branch -a，速度更快且格式固定
            print(f"正在扫描仓库全量分支 (路径: {self.repo_path})...")
            
            # 第一次尝试：for-each-ref (最快)
            result = subprocess.run(
                ["git", "for-each-ref", "--format=%(refname:short)", "refs/heads", "refs/remotes"], 
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=False,
                encoding='utf-8',
                errors='ignore',
                startupinfo=self.startupinfo,
                timeout=30
            )
            
            # 如果 for-each-ref 没结果，尝试传统的 branch -a
            if result.returncode != 0 or not result.stdout.strip():
                print(f"for-each-ref 失败或无输出，尝试 git branch -a...")
                result = subprocess.run(
                    ["git", "branch", "-a"], 
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    encoding='utf-8',
                    errors='ignore',
                    startupinfo=self.startupinfo,
                    timeout=30
                )

            if result.returncode != 0:
                print(f"所有分支枚举手段均失败. Git 错误: {result.stderr}")
                return []

            extracted_branches = []
            seen_appids = set()
            lines = result.stdout.splitlines()
            print(f"Git 返回了 {len(lines)} 个引用/行")

            if not lines:
                print("Git 命令成功执行但未返回任何分支信息。")
                return []

            for line in lines:
                # 去掉前导空格、星号
                branch_name = line.strip().replace("*", "").strip()
                if not branch_name or "HEAD" in branch_name:
                    continue
                
                # 提取 AppID。ManifestHub 这种仓，AppID 通常是分支名末尾
                # origin/2087610 -> 2087610
                parts = branch_name.split('/')
                last_part = parts[-1]
                
                if last_part.isdigit():
                    app_id = last_part
                    if app_id not in seen_appids:
                        extracted_branches.append((app_id, branch_name))
                        seen_appids.add(app_id)
                else:
                    # 备选正则：查找第一个长度>=5的数字序列（AppID通常较长）
                    match = re.search(r'(\d{5,})', last_part)
                    if not match:
                        match = re.search(r'(\d+)', last_part) # 保底方案
                        
                    if match:
                        app_id = match.group(1)
                        if app_id not in seen_appids:
                            extracted_branches.append((app_id, branch_name))
                            seen_appids.add(app_id)

            print(f"成功筛选出 {len(extracted_branches)} 个有效游戏分支")
            
            # 如果获取的分支极多，打印前几个用于确认
            if extracted_branches:
                samples = ", ".join([f"{aid}({name})" for aid, name in extracted_branches[:3]])
                print(f"样例分支: {samples}...")

            # 更新缓存
            formatted_branches = [{"app_id": aid, "branch_name": name} for aid, name in extracted_branches]
            cache_data = {
                "branches": formatted_branches,
                "last_position": len(formatted_branches),
                "last_update": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            self._save_cache(cache_data)
            return extracted_branches
                
        except Exception as e:
            print(f"获取分支发生异常: {str(e)}")
            return []
    
    def checkout_branch(self, branch_name: str) -> Tuple[bool, str]:
        """检出指定分支
        
        Args:
            branch_name: 分支名称
            
        Returns:
            (是否成功, 消息)
        """
        if not self.is_valid_repo():
            print(f"无效的Git仓库: {self.repo_path}")
            return False, "无效的Git仓库"
            
        try:
            print(f"检出分支: {branch_name}")
            
            # 设置超时时间
            timeout = 10  # 10秒超时
            
            try:
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    startupinfo=self.startupinfo,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                error_msg = f"Git检出命令超时 (>{timeout}秒)"
                print(error_msg)
                return False, error_msg
            
            if result.returncode == 0:
                success_msg = f"成功检出分支: {branch_name}"
                print(success_msg)
                return True, success_msg
            else:
                error_msg = f"检出分支失败: {result.stderr}"
                print(error_msg)
                return False, error_msg
                
        except Exception as e:
            error_msg = f"检出分支时出错: {str(e)}"
            print(error_msg)
            return False, error_msg
    
    def find_branch_by_app_id(self, app_id: str) -> Optional[str]:
        """根据AppID查找分支
        
        Args:
            app_id: 游戏的AppID
            
        Returns:
            分支名称，如果不存在则返回None
        """
        if not self.is_valid_repo():
            print(f"无效的Git仓库: {self.repo_path}")
            return None
            
        try:
            print(f"查找appid={app_id}的分支，执行git branch -a命令")
            
            # 设置超时时间
            timeout = 10  # 10秒超时
            
            try:
                result = subprocess.run(
                    ["git", "branch", "-a"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=False,
                    startupinfo=self.startupinfo,
                    timeout=timeout
                )
            except subprocess.TimeoutExpired:
                print(f"Git命令超时 (>{timeout}秒)")
                return None
                
            if result.returncode != 0:
                print(f"Git命令执行失败: {result.stderr}")
                return None
                
            # 优先检查本地分支
            branches = result.stdout.splitlines()
            
            # 首先尝试精确匹配
            for branch in branches:
                branch_name = branch.strip().replace("*", "").strip()
                if app_id == branch_name or app_id == branch_name.split("/")[-1]:
                    print(f"找到精确匹配分支: {branch_name}")
                    # 如果是远程分支，转换为本地分支
                    if branch_name.startswith("remotes/"):
                        branch_name = branch_name.split("/", 2)[-1]
                    return branch_name
            
            # 然后尝试包含匹配
            for branch in branches:
                branch_name = branch.strip().replace("*", "").strip()
                if app_id in branch_name:
                    print(f"找到包含匹配分支: {branch_name}")
                    # 如果是远程分支，转换为本地分支
                    if branch_name.startswith("remotes/"):
                        branch_name = branch_name.split("/", 2)[-1]
                    return branch_name
                    
            print(f"未找到包含 {app_id} 的分支")
            return None
            
        except Exception as e:
            print(f"查找分支出错: {e}")
            return None 

    def fetch_files_from_remote(self, url: str, branch: str, app_id: str, target_dir: str) -> Tuple[bool, str, List[str]]:
        """从远程仓库直接下载指定分支的文件（无需本地克隆）
        
        Args:
            url: 远程仓库 URL (例如 https://github.com/SteamAutoCracks/ManifestHub)
            branch: 分支名称 (通常是 AppID)
            app_id: 游戏 AppID
            target_dir: 下载文件的目标目录
            
        Returns:
            (是否成功, 消息, 下载的文件列表)
        """
        import urllib.request
        import urllib.error
        
        downloaded_files = []
        
        # 解析 GitHub URL
        # https://github.com/SteamAutoCracks/ManifestHub -> SteamAutoCracks/ManifestHub
        if "github.com" in url:
            parts = url.rstrip("/").split("github.com/")
            if len(parts) > 1:
                repo_path = parts[1].rstrip(".git")
            else:
                return False, "无法解析 GitHub URL", []
        else:
            return False, "目前仅支持 GitHub 仓库", []
        
        # 使用 GitHub API 获取分支文件列表
        api_url = f"https://api.github.com/repos/{repo_path}/contents?ref={branch}"
        raw_base_url = f"https://raw.githubusercontent.com/{repo_path}/{branch}"
        
        try:
            print(f"正在从远程获取分支 {branch} 的文件列表...")
            
            # 先尝试获取文件列表
            req = urllib.request.Request(api_url, headers={"User-Agent": "SteamUnlocker/2.0"})
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    import json
                    files_info = json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False, f"分支 {branch} 不存在或无法访问", []
                raise
            
            # 确保目标目录存在
            os.makedirs(target_dir, exist_ok=True)
            
            # 下载需要的文件 (.lua 和 .manifest)
            for file_info in files_info:
                if not isinstance(file_info, dict):
                    continue
                    
                name = file_info.get("name", "")
                if not (name.endswith(".lua") or name.endswith(".manifest")):
                    continue
                
                file_url = f"{raw_base_url}/{name}"
                target_path = os.path.join(target_dir, name)
                
                print(f"正在下载: {name}...")
                try:
                    req = urllib.request.Request(file_url, headers={"User-Agent": "SteamUnlocker/2.0"})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        content = response.read()
                        with open(target_path, 'wb') as f:
                            f.write(content)
                        downloaded_files.append(target_path)
                        print(f"已下载: {name}")
                except Exception as e:
                    print(f"下载 {name} 失败: {e}")
            
            if downloaded_files:
                return True, f"成功下载 {len(downloaded_files)} 个文件", downloaded_files
            else:
                return False, "分支中没有找到 .lua 或 .manifest 文件", []
                
        except Exception as e:
            return False, f"从远程获取文件失败: {str(e)}", []
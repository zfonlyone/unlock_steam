#!/usr/bin/env python3
import asyncio
import os
import shutil
import tempfile
import json
import sys
import time
import traceback
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Set
import datetime

# Import from unlock_script.py - assuming it's in the same directory
try:
    from unlock_script import (
        Logger, process_manifest_folder, copy_manifests_to_steam,
        setup_steamtools, unlock_process, unlock_process_lua
    )
except ImportError as e:
    print(f"错误: 无法导入unlock_script模块: {e}")
    print("请确保unlock_script.py文件位于当前目录")
    sys.exit(1)

# 配置文件路径
CONFIG_FILE = "batch_unlock_config.json"
# 状态文件路径 - 用于断点续传
STATE_FILE = "batch_unlock_state.json"
# 失败列表文件路径
FAILED_LIST_FILE = "failed_appids.json"

# 默认配置
DEFAULT_CONFIG = {
    "repo_path": "D:/Game/steamtools/Manifes/SteamAutoCracks/ManifestHub",  # Git仓库路径
    "steam_path": "C:/Program Files (x86)/Steam",  # Steam安装路径
    "specific_appids": [],  # 指定要解锁的AppID列表，空列表表示全部处理
    "max_retries": 3,  # 单个AppID的最大重试次数
    "batch_size": 10,  # 每批次处理的AppID数量
    "show_details": False,  # 是否显示详细日志
    "auto_clean_failed": True,  # 运行结束时是否自动清理成功的AppID从失败列表中移除
}

# Set up logger with minimal output
class MinimalLogger(Logger):
    """最小化输出的日志类"""
    
    def info(self, message):
        # 只输出特别重要的信息
        pass
        
    def error(self, message):
        # 错误信息需要输出
        print(f"[错误] {message}")
        
    def warning(self, message):
        # 警告也需要输出
        print(f"[警告] {message}")

# 全局日志实例
LOG = MinimalLogger()

# 进度条类
class ProgressBar:
    """简单的进度条实现"""
    
    def __init__(self, total, prefix='', suffix='', decimals=1, length=50, fill='█', print_end='\r'):
        """初始化进度条"""
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.decimals = decimals
        self.length = length
        self.fill = fill
        self.print_end = print_end
        self.start_time = time.time()
        self.current = 0
        
    def update(self, current=None, suffix=None):
        """更新进度条"""
        if current is not None:
            self.current = current
        else:
            self.current += 1
            
        if suffix is not None:
            self.suffix = suffix
            
        percent = ("{0:." + str(self.decimals) + "f}").format(100 * (self.current / float(self.total)))
        filled_length = int(self.length * self.current // self.total)
        bar = self.fill * filled_length + '-' * (self.length - filled_length)
        
        # 计算剩余时间
        elapsed = time.time() - self.start_time
        if self.current > 0:
            eta = elapsed / self.current * (self.total - self.current)
            eta_str = f" ETA: {format_time(eta)}"
        else:
            eta_str = ""
            
        # 构建进度条字符串
        progress_str = f'\r{self.prefix} |{bar}| {percent}% {self.suffix}{eta_str}'
        
        print(progress_str, end=self.print_end)
        
        if self.current == self.total:
            # 完成时打印换行
            print()
            
    def finish(self):
        """完成进度条"""
        elapsed = time.time() - self.start_time
        self.update(self.total, f"完成! 用时: {format_time(elapsed)}")
        print()  # 打印换行

def format_time(seconds):
    """格式化时间"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"

def load_config():
    """加载配置文件，如果不存在则创建默认配置"""
    if not os.path.exists(CONFIG_FILE):
        print(f"配置文件 {CONFIG_FILE} 不存在，创建默认配置...")
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG
        
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 确保所有必要的配置项都存在
        for key, value in DEFAULT_CONFIG.items():
            if key not in config:
                config[key] = value
                
        return config
    except Exception as e:
        print(f"加载配置文件出错: {e}")
        print("使用默认配置...")
        return DEFAULT_CONFIG
        
def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        print(f"配置已保存到 {CONFIG_FILE}")
    except Exception as e:
        print(f"保存配置文件出错: {e}")

def load_state():
    """加载断点续传状态"""
    if not os.path.exists(STATE_FILE):
        return {
            "processed_appids": set(),
            "last_run": "",
            "current_batch": 0
        }
        
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
            
        # 确保processed_appids是集合类型
        state["processed_appids"] = set(state["processed_appids"])
        return state
    except Exception as e:
        print(f"加载状态文件出错: {e}")
        return {
            "processed_appids": set(),
            "last_run": "",
            "current_batch": 0
        }

def save_state(state):
    """保存断点续传状态"""
    # 将集合转换为列表以便JSON序列化
    state_copy = state.copy()
    state_copy["processed_appids"] = list(state["processed_appids"])
    
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state_copy, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存状态文件出错: {e}")

def load_failed_list():
    """加载失败的AppID列表"""
    if not os.path.exists(FAILED_LIST_FILE):
        return {}
        
    try:
        with open(FAILED_LIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"加载失败列表出错: {e}")
        return {}

def save_failed_list(failed_list):
    """保存失败的AppID列表"""
    try:
        with open(FAILED_LIST_FILE, 'w', encoding='utf-8') as f:
            json.dump(failed_list, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存失败列表出错: {e}")

def update_failed_list(app_id, error_message):
    """更新失败的AppID列表"""
    failed_list = load_failed_list()
    
    # 获取当前时间
    now = datetime.datetime.now().isoformat()
    
    # 更新失败信息
    if app_id in failed_list:
        failed_list[app_id]["attempts"] += 1
        failed_list[app_id]["last_error"] = error_message
        failed_list[app_id]["last_attempt"] = now
    else:
        failed_list[app_id] = {
            "attempts": 1,
            "first_failure": now,
            "last_attempt": now,
            "last_error": error_message
        }
        
    save_failed_list(failed_list)

def clean_successful_from_failed(successful_appids):
    """从失败列表中移除成功的AppID"""
    failed_list = load_failed_list()
    
    # 筛选出需要保留的失败AppID
    updated_failed_list = {app_id: data for app_id, data in failed_list.items() 
                          if app_id not in successful_appids}
    
    # 如果有变化，保存更新后的列表
    if len(updated_failed_list) != len(failed_list):
        removed_count = len(failed_list) - len(updated_failed_list)
        print(f"从失败列表中移除了 {removed_count} 个成功的AppID")
        save_failed_list(updated_failed_list)

async def run_command(cmd: List[str], cwd: Optional[str] = None, show_details: bool = False) -> Tuple[bool, str]:
    """Run a shell command asynchronously and return success status and output"""
    if show_details:
        print(f"执行命令: {' '.join(cmd)}")
        
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await proc.communicate()
        
        output = stdout.decode('utf-8', errors='replace')
        error = stderr.decode('utf-8', errors='replace')
        
        if proc.returncode != 0:
            LOG.error(f"命令失败 ({proc.returncode}): {error}")
            return False, error
        return True, output
    except Exception as e:
        LOG.error(f"执行命令失败: {str(e)}")
        return False, str(e)

async def setup_git_worktree(repo_path: Path, branch: str, temp_dir: Path, show_details: bool = False) -> Tuple[bool, Path]:
    """Setup a git worktree for a specific branch in a temporary directory"""
    if show_details:
        print(f"为分支 {branch} 创建工作树")
    
    # 安全处理分支名中的特殊字符
    safe_branch_name = branch.replace("/", "_").replace("\\", "_").replace(":", "_")
    worktree_path = temp_dir / safe_branch_name
    
    # Create worktree
    success, output = await run_command(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=str(repo_path),
        show_details=show_details
    )
    
    if not success:
        LOG.error(f"为分支 {branch} 创建工作树失败")
        return False, Path()
    
    if show_details:
        print(f"已在 {worktree_path} 创建工作树")
    return True, worktree_path

async def cleanup_git_worktree(repo_path: Path, worktree_path: Path, show_details: bool = False) -> bool:
    """Clean up a git worktree"""
    if not worktree_path.exists():
        return True
    
    if show_details:
        print(f"清理工作树: {worktree_path}")
        
    success, output = await run_command(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(repo_path),
        show_details=show_details
    )
    
    if not success:
        LOG.error(f"移除工作树失败: {worktree_path}")
        try:
            # 尝试手动删除目录
            if show_details:
                print("尝试手动删除工作树目录...")
            shutil.rmtree(worktree_path, ignore_errors=True)
            if show_details:
                print(f"已手动删除工作树目录: {worktree_path}")
            return True
        except Exception as e:
            LOG.error(f"手动删除工作树失败: {str(e)}")
            return False
        
    if show_details:
        print(f"已移除工作树: {worktree_path}")
    return True

async def process_app(app_id: str, worktree_path: Path, steam_path: Path, 
                      show_details: bool = False) -> Tuple[bool, str]:
    """Process a single app using the appropriate unlock method"""
    # Check if the worktree contains an app_id.lua file
    lua_file = worktree_path / f"{app_id}.lua"
    
    if show_details:
        print(f"处理AppID {app_id}...")
    
    try:
        if lua_file.exists():
            if show_details:
                print(f"发现 {app_id}.lua 文件，使用直接复制方法")
            # Use the lua copy method
            success = await unlock_process_lua(steam_path, worktree_path, app_id)
        else:
            if show_details:
                print(f"未发现Lua文件，使用depot key方法")
            # Use the original method with depot keys
            success = await unlock_process(steam_path, worktree_path, app_id)
        
        return success if isinstance(success, bool) else False, ""
    except Exception as e:
        error_msg = str(e)
        if show_details:
            print(f"处理AppID {app_id} 时出错: {error_msg}")
            print(traceback.format_exc())
        return False, error_msg

async def extract_app_ids_from_branches(repo_path: Path, show_details: bool = False) -> List[str]:
    """Extract app IDs from branch names in the repository"""
    if show_details:
        print("从分支名称提取AppID...")
    
    success, output = await run_command(
        ["git", "branch", "-r"], 
        cwd=str(repo_path),
        show_details=show_details
    )
    
    if not success:
        LOG.error("获取远程分支列表失败")
        return []
    
    app_ids = set()
    for line in output.splitlines():
        branch = line.strip().replace("* ", "").replace("origin/", "")
        # Extract numeric app ID from branch name
        # Common branch naming patterns include: app_1234567, 1234567_game, 1234567, etc.
        parts = branch.split('_')
        for part in parts:
            # 尝试提取数字部分
            digits_only = ''.join(c for c in part if c.isdigit())
            if len(digits_only) >= 5:  # Most Steam appIDs are at least 5 digits
                app_ids.add(digits_only)
                break
    
    if show_details:
        print(f"从分支名称中提取到 {len(app_ids)} 个AppID")
    return list(app_ids)

async def batch_unlock_process():
    """批量解锁处理的主流程"""
    # 加载配置
    config = load_config()
    show_details = config.get("show_details", False)
    
    # 验证路径
    repo_path = Path(config["repo_path"])
    steam_path = Path(config["steam_path"])
    
    # 检查路径是否存在
    if not repo_path.exists() or not (repo_path / ".git").exists():
        print(f"错误: 无效的Git仓库路径: {repo_path}")
        return
        
    if not steam_path.exists() or not (steam_path / "steam.exe").exists():
        print(f"错误: 无效的Steam安装路径: {steam_path}")
        return
    
    # 加载状态
    state = load_state()
    processed_appids = state["processed_appids"]
    
    # 获取要处理的AppID列表
    app_ids = []
    if config["specific_appids"]:
        app_ids = config["specific_appids"]
        print(f"使用配置文件中指定的 {len(app_ids)} 个AppID")
    else:
        app_ids = await extract_app_ids_from_branches(repo_path, show_details)
        if not app_ids:
            print("错误: 未能从分支名称提取AppID")
            return
        print(f"从Git仓库中提取到 {len(app_ids)} 个AppID")
    
    # 加载失败列表
    failed_list = load_failed_list()
    print(f"历史失败记录: {len(failed_list)} 个AppID")
    
    # 筛选出待处理的AppID
    if processed_appids:
        pending_appids = [app_id for app_id in app_ids if app_id not in processed_appids]
        skipped_count = len(app_ids) - len(pending_appids)
        print(f"跳过已处理的 {skipped_count} 个AppID，剩余 {len(pending_appids)} 个待处理")
        app_ids = pending_appids
    
    # 如果没有待处理的AppID，提示用户
    if not app_ids:
        print("没有待处理的AppID，是否要清除断点续传状态重新开始？")
        response = input("输入 'yes' 确认清除断点续传状态: ")
        if response.lower() == 'yes':
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)
            print("已清除断点续传状态，请重新运行脚本")
        return
    
    # 分批次处理
    batch_size = config.get("batch_size", 10)
    total_batches = (len(app_ids) + batch_size - 1) // batch_size
    current_batch = state.get("current_batch", 0)
    
    # 统计
    successful_appids = set()
    new_failed_appids = {}
    
    print(f"\n开始批量解锁过程 - 共 {len(app_ids)} 个AppID，分 {total_batches} 批次处理")
    
    for batch_index in range(current_batch, total_batches):
        batch_start = batch_index * batch_size
        batch_end = min(batch_start + batch_size, len(app_ids))
        batch_appids = app_ids[batch_start:batch_end]
        
        print(f"\n【批次 {batch_index+1}/{total_batches}】处理 {len(batch_appids)} 个AppID")
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            if show_details:
                print(f"创建临时目录: {temp_dir}")
            
            # 获取分支列表
            success, output = await run_command(
                ["git", "branch", "-a"], 
                cwd=str(repo_path),
                show_details=show_details
            )
            
            if not success:
                print("错误: 获取分支列表失败")
                continue
            
            # 解析分支名称
            branches = []
            for line in output.splitlines():
                branch = line.strip().replace("* ", "")
                if branch:
                    # 保留远程分支信息，但移除 "remotes/" 前缀
                    if branch.startswith("remotes/"):
                        branch = branch.replace("remotes/", "", 1)
                    branches.append(branch)
            
            # 创建进度条
            progress = ProgressBar(len(batch_appids), prefix='进度:', suffix='完成', length=40)
            
            # 处理每个AppID
            for idx, app_id in enumerate(batch_appids):
                # 查找匹配的分支
                matching_branches = [b for b in branches if app_id in b]
                
                # 更新进度条
                progress.update(current=idx, suffix=f"{idx}/{len(batch_appids)} - AppID: {app_id}")
                
                if not matching_branches:
                    LOG.warning(f"没有找到匹配AppID {app_id} 的分支")
                    new_failed_appids[app_id] = "没有匹配的分支"
                    update_failed_list(app_id, "没有匹配的分支")
                    continue
                
                # 使用第一个匹配的分支
                branch = matching_branches[0]
                if show_details:
                    print(f"使用分支 {branch} 处理AppID {app_id}")
                
                # 创建工作树
                success, worktree_path = await setup_git_worktree(repo_path, branch, temp_dir, show_details)
                if not success:
                    LOG.error(f"为AppID {app_id} 创建工作树失败")
                    new_failed_appids[app_id] = "创建工作树失败"
                    update_failed_list(app_id, "创建工作树失败")
                    continue
                
                try:
                    # 处理AppID
                    result, error_msg = await process_app(app_id, worktree_path, steam_path, show_details)
                    
                    if result:
                        successful_appids.add(app_id)
                        processed_appids.add(app_id)
                    else:
                        new_failed_appids[app_id] = error_msg or "处理失败，无详细错误信息"
                        update_failed_list(app_id, error_msg or "处理失败，无详细错误信息")
                except Exception as e:
                    LOG.error(f"处理AppID {app_id} 时发生意外错误: {str(e)}")
                    if show_details:
                        print(traceback.format_exc())
                    new_failed_appids[app_id] = str(e)
                    update_failed_list(app_id, str(e))
                finally:
                    # 清理工作树
                    await cleanup_git_worktree(repo_path, worktree_path, show_details)
                    
                    # 更新状态
                    state["processed_appids"] = processed_appids
                    state["last_run"] = datetime.datetime.now().isoformat()
                    state["current_batch"] = batch_index
                    save_state(state)
            
            # 完成进度条
            progress.finish()
        
        # 显示批次摘要
        print(f"\n批次 {batch_index+1}/{total_batches} 处理完成!")
        print(f"成功: {len(successful_appids)} 个AppID")
        print(f"失败: {len(new_failed_appids)} 个AppID")
        
        # 更新状态
        state["current_batch"] = batch_index + 1
        save_state(state)
    
    # 清理成功的AppID从失败列表中
    if config.get("auto_clean_failed", True) and successful_appids:
        clean_successful_from_failed(successful_appids)
    
    # 显示总结
    print("\n========================")
    print("  批量解锁处理完成!")
    print("========================")
    print(f"总共处理: {len(app_ids)} 个AppID")
    print(f"成功解锁: {len(successful_appids)} 个")
    print(f"解锁失败: {len(new_failed_appids)} 个")
    
    # 显示失败的AppID列表
    if new_failed_appids:
        print("\n失败的AppID列表:")
        for i, (app_id, error) in enumerate(list(new_failed_appids.items())[:10]):
            print(f"  {i+1}. {app_id}: {error[:50]}..." if len(error) > 50 else f"  {i+1}. {app_id}: {error}")
        
        if len(new_failed_appids) > 10:
            print(f"  ... 以及 {len(new_failed_appids)-10} 个更多失败的AppID")
        
        print(f"\n失败记录已保存到 {FAILED_LIST_FILE}")
        print("可以修改配置后重试失败的AppID")

async def main():
    """主函数"""
    print("\n=======================================")
    print("   Steam游戏批量解锁工具 v2.0")
    print("=======================================")
    
    try:
        # 检查是否有命令行参数
        if len(sys.argv) > 1:
            if sys.argv[1] == "--reset":
                # 重置状态
                if os.path.exists(STATE_FILE):
                    os.remove(STATE_FILE)
                print("已清除断点续传状态")
                
                # 如果有第二个参数，也清除失败列表
                if len(sys.argv) > 2 and sys.argv[2] == "--clear-failed":
                    if os.path.exists(FAILED_LIST_FILE):
                        os.remove(FAILED_LIST_FILE)
                    print("已清除失败AppID列表")
                    
                print("请重新运行脚本，不带参数")
                return
            elif sys.argv[1] == "--init-config":
                # 初始化配置
                save_config(DEFAULT_CONFIG)
                print(f"已初始化配置文件 {CONFIG_FILE}")
                print("请编辑配置文件后运行脚本")
                return
            elif sys.argv[1] == "--help":
                # 显示帮助
                print("用法:")
                print("  python batch_unlock.py             - 运行批量解锁")
                print("  python batch_unlock.py --reset     - 重置断点续传状态")
                print("  python batch_unlock.py --reset --clear-failed - 重置状态并清除失败列表")
                print("  python batch_unlock.py --init-config - 初始化默认配置文件")
                print("  python batch_unlock.py --help      - 显示帮助")
                return
        
        # 执行批量解锁过程
        await batch_unlock_process()
    except KeyboardInterrupt:
        print("\n操作已被用户中断")
    except Exception as e:
        print(f"执行过程中发生错误: {str(e)}")
        print("详细错误信息:")
        traceback.print_exc()

if __name__ == "__main__":
    try:
        if sys.version_info < (3, 7):
            print("错误: 此脚本需要Python 3.7或更高版本")
            sys.exit(1)
            
        # 运行主程序
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n操作已被用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"执行过程中发生错误: {str(e)}")
        print("详细错误信息:")
        traceback.print_exc()
        sys.exit(1) 
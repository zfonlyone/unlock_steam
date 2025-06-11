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
from typing import List, Tuple, Optional
import datetime

from models import unlock_process, unlock_process_lua

# 基础Logger类
class Logger:
    """基础日志类"""
    def info(self, message):
        pass
        
    def error(self, message):
        pass
        
    def warning(self, message):
        pass

# 配置文件路径
CONFIG_FILE = "batch_unlock_config.json"
# 状态文件路径 - 用于断点续传
STATE_FILE = "batch_unlock_state.json"
# 失败列表文件路径
FAILED_LIST_FILE = "batch_unlock_failed_appids.json"

# Set up logger with minimal output
class MinimalLogger(Logger):
    """最小化输出的日志类"""
    
    def info(self, message):
        # 输出重要信息
        if "成功" in message or "失败" in message:
            print(f"[信息] {message}")
        
    def error(self, message):
        # 只输出关键错误
        print(f"[错误] {message}")
        
    def warning(self, message):
        # 不输出警告
        pass

# 全局日志实例
LOG = MinimalLogger()

# 默认配置
DEFAULT_CONFIG = {
    "repo_path": "D:/Game/steamtools/Manifes/SteamAutoCracks/ManifestHub",  # Git仓库路径
    "steam_path": "C:/Program Files (x86)/Steam",  # Steam安装路径
    "specific_appids": [],  # 指定要解锁的AppID列表，空列表表示全部处理（这里设置为CSGO的AppID进行测试）
    "max_retries": 3,  # 单个AppID的最大重试次数
    "batch_size": 1000,  # 每批次处理的AppID数量
    "show_details": True,  # 是否显示详细日志
    "auto_clean_failed": True,  # 运行结束时是否自动清理成功的AppID从失败列表中移除
}

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

async def run_command(cmd: List[str], cwd: Optional[str] = None) -> Tuple[bool, str]:
    """Run a shell command asynchronously without any output"""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd
        )
        stdout, stderr = await proc.communicate()
        
        output = stdout.decode('utf-8', errors='replace')
        
        if proc.returncode != 0:
            return False, ""
        return True, output
    except Exception:
        return False, ""

async def setup_git_worktree(repo_path: Path, branch: str, temp_dir: Path) -> Tuple[bool, Path]:
    """Setup a git worktree for a specific branch in a temporary directory"""
    # 安全处理分支名中的特殊字符
    safe_branch_name = branch.replace("/", "_").replace("\\", "_").replace(":", "_")
    worktree_path = temp_dir / safe_branch_name
    
    # Create worktree
    success, output = await run_command(
        ["git", "worktree", "add", str(worktree_path), branch],
        cwd=str(repo_path)
    )
    
    if not success:
        return False, Path()
    
    return True, worktree_path

async def cleanup_git_worktree(repo_path: Path, worktree_path: Path) -> bool:
    """Clean up a git worktree"""
    if not worktree_path.exists():
        return True
    
    success, output = await run_command(
        ["git", "worktree", "remove", "--force", str(worktree_path)],
        cwd=str(repo_path)
    )
    
    if not success:
        try:
            # 尝试手动删除目录
            shutil.rmtree(worktree_path, ignore_errors=True)
            return True
        except Exception:
            return False
        
    return True

async def process_app(app_id: str, worktree_path: Path, steam_path: Path, 
                      show_details: bool = False) -> Tuple[bool, str]:
    """直接复制文件从工作目录到Steam目录"""
    try:
        # 设置路径
        st_path = steam_path / "config" / "stplug-in"
        st_path.mkdir(exist_ok=True)
        
        depot_cache = steam_path / "config" / "depotcache"
        depot_cache.mkdir(exist_ok=True)
        
        # 复制.lua文件(如果存在)
        lua_file = worktree_path / f"{app_id}.lua"
        success = False
        
        if lua_file.exists():
            dst_lua = st_path / f"{app_id}.lua"
            shutil.copy2(str(lua_file), str(dst_lua))
            success = True
        
        # 复制所有manifest文件
        for manifest_file in worktree_path.glob("*.manifest"):
            dst_manifest = depot_cache / manifest_file.name
            if not dst_manifest.exists():
                shutil.copy2(str(manifest_file), str(dst_manifest))
                success = True
        
        return success, ""
    except Exception as e:
        return False, str(e)

async def extract_app_ids_from_branches(repo_path: Path) -> List[str]:
    """Extract app IDs from branch names in the repository"""
    success, output = await run_command(
        ["git", "branch", "-r"], 
        cwd=str(repo_path)
    )
    
    if not success:
        return []
    
    app_ids = set()
    for line in output.splitlines():
        branch = line.strip().replace("* ", "").replace("origin/", "")
        parts = branch.split('_')
        for part in parts:
            digits_only = ''.join(c for c in part if c.isdigit())
            if len(digits_only) >= 5:
                app_ids.add(digits_only)
                break
    
    return list(app_ids)

async def batch_unlock_process():
    """批量解锁处理的主流程 - 极简版"""
    # 加载配置
    config = load_config()
    
    # 验证路径
    repo_path = Path(config["repo_path"])
    steam_path = Path(config["steam_path"])
    
    # 检查路径是否存在
    if not repo_path.exists() or not (repo_path / ".git").exists():
        print("错误: 无效的Git仓库路径")
        return
        
    if not steam_path.exists() or not (steam_path / "steam.exe").exists():
        print("错误: 无效的Steam安装路径")
        return
    
    # 加载状态
    state = load_state()
    processed_appids = state["processed_appids"]
    
    # 获取要处理的AppID列表
    app_ids = []
    if config["specific_appids"]:
        app_ids = config["specific_appids"]
        print(f"处理 {len(app_ids)} 个指定AppID")
    else:
        app_ids = await extract_app_ids_from_branches(repo_path)
        if not app_ids:
            print("错误: 未能提取AppID")
            return
        print(f"提取到 {len(app_ids)} 个AppID")
    
    # 筛选出待处理的AppID
    if processed_appids:
        pending_appids = [app_id for app_id in app_ids if app_id not in processed_appids]
        print(f"待处理: {len(pending_appids)} 个")
        app_ids = pending_appids
    
    # 如果没有待处理的AppID，退出
    if not app_ids:
        print("没有待处理的AppID")
        return
    
    # 分批次处理
    batch_size = config.get("batch_size", 10)
    total_batches = (len(app_ids) + batch_size - 1) // batch_size
    current_batch = state.get("current_batch", 0)
    
    # 统计
    successful_appids = set()
    new_failed_appids = {}
    
    # 总进度计算变量
    total_count = len(app_ids)
    processed_count = 0
    start_time = time.time()
    
    print(f"开始处理 {total_count} 个AppID...")
    
    for batch_index in range(current_batch, total_batches):
        batch_start = batch_index * batch_size
        batch_end = min(batch_start + batch_size, len(app_ids))
        batch_appids = app_ids[batch_start:batch_end]
        
        # 显示批次进度
        print(f"批次: {batch_index+1}/{total_batches}")
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir_str:
            temp_dir = Path(temp_dir_str)
            
            # 获取分支列表
            success, output = await run_command(
                ["git", "branch", "-a"], 
                cwd=str(repo_path)
            )
            
            if not success:
                continue
            
            # 解析分支名称
            branches = []
            for line in output.splitlines():
                branch = line.strip().replace("* ", "")
                if branch:
                    if branch.startswith("remotes/"):
                        branch = branch.replace("remotes/", "", 1)
                    branches.append(branch)
            
            # 处理每个AppID
            for idx, app_id in enumerate(batch_appids):
                # 显示当前进度
                processed_count += 1
                percent = int(processed_count / total_count * 100)
                elapsed = time.time() - start_time
                
                # 估算剩余时间
                if processed_count > 1:
                    eta = (elapsed / processed_count) * (total_count - processed_count)
                    eta_str = format_time(eta)
                else:
                    eta_str = "计算中..."
                
                print(f"进度: {percent}% [{processed_count}/{total_count}] - 当前: {app_id} - 剩余时间: {eta_str}", end="\r")
                
                # 查找匹配的分支
                matching_branches = [b for b in branches if app_id in b]
                
                if not matching_branches:
                    new_failed_appids[app_id] = "没有匹配的分支"
                    update_failed_list(app_id, "没有匹配的分支")
                    continue
                
                # 使用第一个匹配的分支
                branch = matching_branches[0]
                
                # 创建工作树
                success, worktree_path = await setup_git_worktree(repo_path, branch, temp_dir)
                if not success:
                    new_failed_appids[app_id] = "创建工作树失败"
                    update_failed_list(app_id, "创建工作树失败")
                    continue
                
                try:
                    # 处理AppID
                    result, error_msg = await process_app(app_id, worktree_path, steam_path)
                    
                    if result:
                        successful_appids.add(app_id)
                        processed_appids.add(app_id)
                    else:
                        new_failed_appids[app_id] = error_msg or "处理失败"
                        update_failed_list(app_id, error_msg or "处理失败")
                except Exception as e:
                    new_failed_appids[app_id] = str(e)
                    update_failed_list(app_id, str(e))
                finally:
                    # 清理工作树
                    await cleanup_git_worktree(repo_path, worktree_path)
                    
                    # 更新状态
                    state["processed_appids"] = processed_appids
                    state["last_run"] = datetime.datetime.now().isoformat()
                    state["current_batch"] = batch_index
                    save_state(state)
        
        # 更新状态
        state["current_batch"] = batch_index + 1
        save_state(state)
        
        # 批次完成后换行
        print()
    
    # 清理成功的AppID从失败列表中
    if config.get("auto_clean_failed", True) and successful_appids:
        clean_successful_from_failed(successful_appids)
    
    # 计算总用时
    total_time = time.time() - start_time
    time_str = format_time(total_time)
    
    # 显示总结
    print(f"处理完成! 总用时: {time_str}")
    print(f"成功: {len(successful_appids)} 个, 失败: {len(new_failed_appids)} 个")

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
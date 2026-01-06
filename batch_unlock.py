import asyncio
import os
import shutil
import tempfile
import json
import sys
import time
import traceback
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import datetime
import urllib.request
import urllib.error
import re

# 增加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from models import UnlockModel, ConfigModel, DataManager, GamesDatabase

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
    "unlock_source": "remote",  # 解锁来源: local (本地Git) 或 remote (远程API/GitHub)
    "repo_path": "",  # 本地 Git 仓库路径 (用于 local 模式)
    "repo_url": "https://github.com/ManifestHub/ManifestHub",  # 远程仓库 URL
    "steam_path": "C:/Program Files (x86)/Steam",  # Steam安装路径
    "api_key": "",  # ManifestHub API 密钥
    "github_token": "",  # GitHub Token (增加API调用限额)
    "specific_appids": [],  # 指定要解锁的AppID列表，空列表表示自动扫描
    "max_retries": 3,
    "batch_size": 100,  # 并发执行的批次大小
    "show_details": True,
    "auto_clean_failed": True,
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

async def extract_app_ids_from_db():
    """从本地数据库 games_data.db 提取 AppID 列表"""
    try:
        db_path = Path("games_data.db")
        if not db_path.exists():
            return []
            
        data_manager = DataManager()
        games = data_manager.get_all_games()
        app_ids = [str(g.get("app_id")) for g in games if g.get("app_id")]
        return list(set(app_ids))
    except Exception as e:
        print(f"从本地数据库读取失败: {e}")
        return []

async def extract_app_ids_from_remote(repo_url: str, token: str = "") -> List[str]:
    """从 GitHub API 获取分支列表中的 AppID"""
    if "github.com" not in repo_url:
        return []
    
    parts = repo_url.rstrip("/").split("github.com/")
    repo_path = parts[1].rstrip(".git") if len(parts) > 1 else ""
    if not repo_path:
        return []
        
    api_url = f"https://api.github.com/repos/{repo_path}/branches?per_page=100"
    headers = {"User-Agent": "SteamUnlocker/2.0", "Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
        
    app_ids = set()
    try:
        page = 1
        while True:
            url = f"{api_url}&page={page}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as response:
                branches_info = json.loads(response.read().decode('utf-8'))
                if not branches_info:
                    break
                
                for branch in branches_info:
                    name = branch.get("name", "")
                    # 匹配数字 AppID (通常是全数字或 st_数字)
                    match = re.search(r'(\d{5,})', name)
                    if match:
                        app_ids.add(match.group(1))
                
                if len(branches_info) < 100:
                    break
                page += 1
    except Exception as e:
        print(f"获取远程分支列表失败: {e}")
        
    return list(app_ids)

def print_progress_bar(percent, msg="", start_time=None, total=0, processed=0):
    """打印 ASCII 进度条"""
    # 静态变量模拟，记录上次百分比
    if not hasattr(print_progress_bar, "last_percent"):
        print_progress_bar.last_percent = 0
        
    if percent == -1:
        percent = print_progress_bar.last_percent
    else:
        print_progress_bar.last_percent = percent

    bar_width = 30
    filled = int(bar_width * percent / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    elapsed = time.time() - start_time if start_time else 0
    
    # 使用 \r 覆盖当前行，msg 限制长度
    info = f" {percent:3d}% | {elapsed:.1f}s | {processed}/{total} | {msg[:30]:<30}"
    print(f"\r[{bar}]{info}", end="", flush=True)
    if percent >= 100:
        print()

async def batch_unlock_process():
    """批量解锁处理的主流程 - 并发增强版"""
    # 加载配置
    config = load_config()
    
    # 初始化模型
    unlock_model = UnlockModel(config)
    data_manager = DataManager()
    steam_path = Path(unlock_model.get_steam_path())
    
    if not steam_path.exists():
        print(f"错误: Steam 路径无效: {steam_path}")
        return
        
    # 加载断点续传状态
    state = load_state()
    processed_appids = state.get("processed_appids", set())
    
    # 获取要处理的AppID列表
    app_ids = []
    if config.get("specific_appids"):
        app_ids = config["specific_appids"]
        print(f"处理 {len(app_ids)} 个指定AppID")
    else:
        source = config.get("unlock_source", "remote")
        if source == "local":
            repo_path = Path(config.get("repo_path", ""))
            if not repo_path.exists():
                print("错误: 本地仓库路径无效")
                return
            app_ids = await extract_app_ids_from_branches(repo_path)
        else:
            # 优先尝试从本地数据库获取
            print("正在从本地数据库提取 AppID 列表...")
            app_ids = await extract_app_ids_from_db()
            
            if not app_ids:
                print(f"本地数据库为空或不存在，正在从云端获取: {config['repo_url']}...")
                app_ids = await extract_app_ids_from_remote(config["repo_url"], config.get("github_token", ""))
            
        if not app_ids:
            print("错误: 未能获取到 AppID 列表")
            return
        print(f"共发现 {len(app_ids)} 个游戏")
    
    # 筛选待处理
    pending_appids = [aid for aid in app_ids if aid not in processed_appids]
    total_count = len(pending_appids)
    
    if total_count == 0:
        print("🎉 所有游戏已处理完成！")
        return
        
    print(f"待处理: {total_count} 个 (已跳过 {len(processed_appids)} 个)")
    
    # 分批并发处理
    batch_size = config.get("batch_size", 100)
    start_time = time.time()
    successful_count = 0
    
    print(f"\n{'='*65}")
    print(f"🚀 开始批处理 - 模式: {config.get('unlock_source')} | 并发: {batch_size}")
    print(f"{'='*65}\n")

    # 为了保持断点续传，我们按批次调用并发解锁
    for i in range(0, total_count, batch_size):
        current_batch = pending_appids[i:i + batch_size]
        
        def progress_callback(msg, percent):
            # 将批次的百分比映射到全局百分比
            global_percent = int(((i + (percent/100 * len(current_batch))) / total_count) * 100)
            print_progress_bar(global_percent, msg, start_time, total_count, i + int(percent/100 * len(current_batch)))

        # 构建清单映射
        app_data = {}
        all_games = data_manager.get_all_games()
        game_map = {str(g['app_id']): g for g in all_games}
        for aid in current_batch:
            game = game_map.get(str(aid))
            if game and 'depots' in game:
                m_ids = [f"{did}_{d['manifest_id']}" for did, d in game['depots'].items() if d.get('manifest_id')]
                if m_ids:
                    app_data[str(aid)] = m_ids

        # 调用并发解锁模型
        batch_results = await unlock_model.batch_unlock_concurrent(current_batch, progress_callback, app_data=app_data)
        
        # 处理结果并保存状态
        batch_success = 0
        for aid, (success, msg) in batch_results.items():
            if success:
                batch_success += 1
                processed_appids.add(aid)
                successful_count += 1
            else:
                update_failed_list(aid, msg)
        
        # 保存断点
        state["processed_appids"] = processed_appids
        state["last_run"] = datetime.datetime.now().isoformat()
        save_state(state)
    
    # 完成
    print_progress_bar(100, "全部处理完成", start_time, total_count, total_count)
    
    elapsed = time.time() - start_time
    print(f"\n{'='*65}")
    print(f"✅ 处理完成！")
    print(f"   📊 成功: {successful_count} | 失败: {total_count - successful_count} | 总计: {total_count}")
    print(f"   ⏱️  总耗时: {format_time(elapsed)}")
    print(f"{'='*65}\n")
    
    if config.get("auto_clean_failed") and successful_count > 0:
        # 这里逻辑稍微改动，传入已处理集合即可
        clean_successful_from_failed(processed_appids)

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
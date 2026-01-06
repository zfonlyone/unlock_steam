from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from typing import List, Dict, Any, Optional
import os
import json

class GitController(QObject):
    """Git操作控制器(Controller层)"""
    
    # 进度信号
    progressUpdated = pyqtSignal(str, int)  # 消息和进度百分比
    operationFinished = pyqtSignal(bool, str)  # 成功/失败, 消息
    
    def __init__(self, data_model, git_model, config_model, view):
        """初始化控制器
        
        Args:
            data_model: 数据模型(DataManager)
            git_model: Git模型(GitModel)
            config_model: 配置模型(ConfigModel)
            view: 视图(MainWindow)
        """
        super().__init__()
        self.data_model = data_model
        self.git_model = git_model
        self.config_model = config_model
        self.view = view
        
        # 连接视图信号到控制器方法
        self.view.updateListRequested.connect(self.update_branch_list)
        
        # 连接控制器信号到视图更新方法
        self.progressUpdated.connect(self.update_progress)
        self.operationFinished.connect(self.handle_operation_completed)
    
    def update_branch_list(self):
        """更新分支列表，支持多仓库同步"""
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            QMessageBox.warning(
                self.view, 
                "配置错误", 
                "配置无效，请先配置Steam路径。"
            )
            return
        
        # 获取所有启用的仓库
        enabled_repos_raw = self.config_model.get_enabled_repositories()
        
        # 兼容逻辑：如果用户设置了本地路径，优先使用本地路径，而不是默认远程仓库
        legacy_path = self.config_model.get("manifest_repo_path", "")
        if legacy_path and os.path.exists(os.path.join(legacy_path, ".git")):
            # 如果只有默认的 ManifestHub 远程仓库，替换为用户的本地仓库
            if len(enabled_repos_raw) == 1 and enabled_repos_raw[0].get("name") == "ManifestHub":
                enabled_repos_raw = [{"name": "LocalRepo", "type": "local", "path": legacy_path, "enabled": True}]
                print(f"[GitController] 使用用户配置的本地仓库: {legacy_path}")
        
        # 去重：按名称去重，防止重复处理
        seen_names = set()
        unique_repos = []
        for repo in enabled_repos_raw:
            name = repo.get("name", "Unknown")
            if name not in seen_names:
                seen_names.add(name)
                unique_repos.append(repo)
        enabled_repos_raw = unique_repos
        
        print(f"[GitController] 待处理仓库列表: {[r.get('name') for r in enabled_repos_raw]}")
            
        if not enabled_repos_raw:

            QMessageBox.warning(
                self.view,
                "未配置仓库",
                "请先在设置中添加并启用至少一个清单仓库。"
            )
            return
            
        # 显示确认对话框
        result = QMessageBox.question(
            self.view,
            "确认更新",
            f"将从 {len(enabled_repos_raw)} 个仓库获取分支信息，这可能需要一些时间，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 禁用按钮
        self.view.enable_buttons(False)
        self.view.set_status("正在准备同步仓库...")
        
        # 创建进度对话框
        progress_dialog = QProgressDialog("正在准备同步数据...", "取消", 0, 100, self.view)
        progress_dialog.setWindowTitle("数据同步中")
        progress_dialog.setModal(True)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.show()
        
        import threading
        
        def fetch_task():
            try:
                all_aggregated_branches = []
                total_repos = len(enabled_repos_raw)
                
                for i, repo in enumerate(enabled_repos_raw):
                    repo_name = repo.get("name", "Unknown")
                    repo_path = repo.get("path", "")
                    repo_type = repo.get("type", "local")
                    repo_url = repo.get("url", "")
                    
                    self.progressUpdated.emit(f"正在处理仓库: {repo_name}...", int((i / total_repos) * 100))
                    
                    branches = []
                    
                    # 优先使用远程直接获取（无需克隆）
                    if repo_type == "remote" and repo_url:
                        print(f"[GitController] 直接从远程获取分支: {repo_url}")
                        self.progressUpdated.emit(f"正在从远程获取: {repo_name}...", int((i / total_repos) * 100))
                        branches = self.git_model.fetch_remote_branches(repo_url)
                    elif repo_path:
                        # 本地仓库：使用传统方式
                        abs_repo_path = os.path.abspath(repo_path)
                        if os.path.exists(os.path.join(abs_repo_path, ".git")):
                            self.git_model.repo_path = abs_repo_path
                            self.progressUpdated.emit(f"正在扫描本地仓库: {repo_name}...", int((i / total_repos) * 100))
                            print(f"[GitController] 正在扫描本地仓库: {abs_repo_path}")
                            branches = self.git_model.fetch_branches(use_cache=False, sync=True)
                        else:
                            print(f"跳过无效本地仓库: {repo_name} ({abs_repo_path})")
                            continue
                    else:
                        print(f"跳过无效仓库配置: {repo_name}")
                        continue
                    
                    # 给分支名加上仓库标识
                    prefixed_branches = [(app_id, f"{repo_name}/{branch}") for app_id, branch in branches]
                    all_aggregated_branches.extend(prefixed_branches)
                    print(f"[GitController] 仓库 {repo_name} 获取了 {len(branches)} 个分支")
                
                if not all_aggregated_branches and total_repos > 0:
                    msg = "扫描完成，但未发现任何以 AppID 命名的分支。请确认仓库配置是否包含 AppID 分支。"
                    self.operationFinished.emit(False, msg)
                    return

                # 更新游戏数据
                self.progressUpdated.emit(f"正在向数据库同步 {len(all_aggregated_branches)} 条记录...", 85)
                self.data_model.update_games_from_branches(all_aggregated_branches, auto_save=True)
                
                # 重新加载并显示最新数据
                self.progressUpdated.emit("正在刷新界面显示...", 95)
                games = self.data_model.get_all_games()
                QTimer.singleShot(0, lambda: self.view.update_table(games))
                
                msg = f"更新完成：共从 {total_repos} 个仓库获取了 {len(all_aggregated_branches)} 个分支。"
                self.operationFinished.emit(True, msg)
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.operationFinished.emit(False, f"同步发生未知异常: {str(e)}")
            finally:
                QTimer.singleShot(0, progress_dialog.close)
        
        threading.Thread(target=fetch_task, daemon=True).start()
    
    
    def cancel_operation(self):
        """取消操作"""
        # 这里应该实现取消Git操作的逻辑
        # 但由于GitModel目前没有实现取消操作的方法，暂时只显示消息
        self.view.set_status("操作已取消")
        
        # 启用按钮
        self.view.enable_buttons(True)
    
    def update_progress(self, message: str, progress: int):
        """更新进度信息
        
        Args:
            message: 进度消息
            progress: 进度百分比
        """
        self.view.set_status(f"{message} ({progress}%)")
    
    def handle_operation_completed(self, success: bool, message: str):
        """处理操作完成事件
        
        Args:
            success: 是否成功
            message: 消息
        """
        # 启用按钮
        self.view.enable_buttons(True)
        
        # 显示结果消息
        self.view.set_status(message)
        
        if success:
            # 显示操作成功的消息对话框
            QMessageBox.information(
                self.view,
                "操作完成",
                message
            )
        else:
            # 显示错误消息
            QMessageBox.critical(
                self.view,
                "操作失败",
                message
            ) 
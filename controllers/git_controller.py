from PyQt5.QtWidgets import QMessageBox, QProgressDialog
from PyQt5.QtCore import QObject, pyqtSignal, QTimer
from typing import List, Dict, Any, Optional

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
        """更新分支列表"""
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            QMessageBox.warning(
                self.view, 
                "配置错误", 
                "配置无效，请先配置清单仓库路径。"
            )
            return
        
        # 显示确认对话框
        result = QMessageBox.question(
            self.view,
            "确认更新",
            "更新分支列表可能需要一些时间，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 禁用按钮，避免重复操作
        self.view.enable_buttons(False)
        
        # 显示进度信息
        self.view.set_status("正在获取仓库分支信息...")
        
        # 创建进度对话框
        progress_dialog = QProgressDialog("正在更新分支列表...", "取消", 0, 100, self.view)
        progress_dialog.setWindowTitle("更新进度")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        # 连接取消按钮信号
        progress_dialog.canceled.connect(self.cancel_operation)
        
        # 导入线程模块
        import threading
        
        # 定义任务函数
        def fetch_branches_task():
            try:
                # 设置进度
                self.progressUpdated.emit("正在获取分支信息...", 10)
                
                # 获取仓库路径
                repo_path = self.config_model.get("manifest_repo_path", "")
                
                # 获取分支列表 - 修改这里，设置一个很大的batch_size以获取全部分支
                branches = self.git_model.fetch_branches(use_cache=False, batch_size=100000)
                
                # 设置进度
                self.progressUpdated.emit("正在更新游戏数据...", 50)
                
                # 更新游戏数据
                self.data_model.update_games_from_branches(branches, auto_save=True)
                
                # 获取所有游戏
                games = self.data_model.get_all_games()
                
                # 设置进度
                self.progressUpdated.emit("正在更新界面...", 90)
                
                # 在主线程中更新UI
                QTimer.singleShot(0, lambda: self.view.update_table(games))
                
                # 完成操作
                self.operationFinished.emit(True, f"分支列表更新完成，共添加/更新了{len(branches)}个分支。")
                
                # 关闭进度对话框
                if progress_dialog and progress_dialog.isVisible():
                    QTimer.singleShot(0, progress_dialog.close)
                
            except Exception as e:
                # 发送错误信号
                self.operationFinished.emit(False, f"更新分支列表失败: {str(e)}")
                
                # 关闭进度对话框
                if progress_dialog and progress_dialog.isVisible():
                    QTimer.singleShot(0, progress_dialog.close)
        
        # 在单独的线程中运行任务
        thread = threading.Thread(target=fetch_branches_task)
        thread.start()
    
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
        
        if not success:
            # 显示错误消息
            QMessageBox.critical(
                self.view,
                "操作失败",
                message
            ) 
import asyncio
from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QDialog, QProgressDialog, QInputDialog
from PyQt5.QtCore import QPoint, QObject, pyqtSignal, QTimer
from typing import List, Dict, Any, Optional
from PyQt5.QtWidgets import QApplication
import threading
import time
import random


class UnlockController(QObject):
    """解锁功能控制器(Controller层)"""
    
    # 进度信号
    progressUpdated = pyqtSignal(str, int)  # 消息和进度百分比
    unlockCompleted = pyqtSignal(bool, str, str)  # 成功/失败, 消息, app_id
    
    def __init__(self, data_model, unlock_model, config_model, view):
        """初始化控制器
        
        Args:
            data_model: 数据模型(DataManager)
            unlock_model: 解锁模型(UnlockModel)
            config_model: 配置模型(ConfigModel)
            view: 视图(MainWindow)
        """
        super().__init__()
        self.data_model = data_model
        self.unlock_model = unlock_model
        self.config_model = config_model
        self.view = view
        
        # 连接信号
        self.view.checkUnlockStatusRequested.connect(self.check_all_unlocked_games)
    
    def unlock_game(self, app_id: str):
        """解锁游戏
        
        Args:
            app_id: 游戏AppID
        """
        # 获取游戏信息
        game = self.data_model.get_game(app_id)
        if not game:
            QMessageBox.warning(
                self.view,
                "解锁失败",
                f"找不到游戏 {app_id} 的信息"
            )
            return
        
        # 获取数据库列表
        databases = game.get("databases", [])
        if not databases:
            QMessageBox.warning(
                self.view,
                "解锁失败",
                f"游戏 {app_id} 没有关联的数据库"
            )
            return
        
        # 如果有多个数据库，让用户选择
        database_name = ""
        if len(databases) > 1:
            from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton
            
            # 创建对话框
            dialog = QDialog(self.view)
            dialog.setWindowTitle("选择数据库")
            layout = QVBoxLayout()
            
            # 添加说明标签
            layout.addWidget(QLabel(f"请选择游戏 {app_id} 的数据库:"))
            
            # 添加列表
            list_widget = QListWidget()
            for db in databases:
                list_widget.addItem(db)
            layout.addWidget(list_widget)
            
            # 添加按钮
            button = QPushButton("确定")
            button.clicked.connect(dialog.accept)
            layout.addWidget(button)
            
            # 设置布局并显示对话框
            dialog.setLayout(layout)
            result = dialog.exec_()
            
            # 获取选择的数据库
            if result == QDialog.Accepted and list_widget.currentItem():
                database_name = list_widget.currentItem().text()
            else:
                return
        else:
            # 只有一个数据库，直接使用
            database_name = databases[0]
        
        # 启动解锁过程
        self.start_unlock_process(app_id, database_name)
    
    def start_unlock_process(self, app_id: str, database_name: str):
        """启动游戏解锁过程
        
        Args:
            app_id: 游戏AppID
            database_name: 数据库名称
        """
        # 禁用按钮，防止重复操作
        self.view.enable_buttons(False)
        
        # 显示进度信息
        self.view.set_status(f"正在解锁游戏 {app_id}...")
        
        # 创建并显示进度对话框
        progress_dialog = QProgressDialog("正在解锁游戏...", "取消", 0, 100, self.view)
        progress_dialog.setWindowTitle("解锁进度")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        # 连接进度信号
        self.progressUpdated.connect(lambda msg, val: progress_dialog.setLabelText(msg))
        self.progressUpdated.connect(lambda msg, val: progress_dialog.setValue(val))
        
        # 创建事件循环
        async def unlock_task():
            try:
                # 执行解锁操作
                success, message = await self.unlock_model.unlock_game_async(
                    app_id, 
                    database_name,
                    lambda msg, val: self.progressUpdated.emit(msg, val)
                )
                
                # 更新游戏状态
                if success:
                    self.data_model.set_unlock_status(app_id, True, auto_save=True)
                
                # 发送完成信号
                self.unlockCompleted.emit(success, message, app_id)
            except Exception as e:
                # 发送错误信号
                self.unlockCompleted.emit(False, f"解锁过程中发生错误: {str(e)}", app_id)
                
        # 创建事件循环并在单独的线程中运行任务
        def run_async_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(unlock_task())
        
        # 在单独的线程中运行事件循环
        thread = threading.Thread(target=run_async_task)
        thread.start()
    
    def remove_unlock(self, app_id: str):
        """取消解锁游戏
        
        Args:
            app_id: 游戏AppID
        """
        # 获取游戏信息
        game = self.data_model.get_game(app_id)
        if not game:
            QMessageBox.warning(
                self.view,
                "取消解锁失败",
                f"找不到游戏 {app_id} 的信息"
            )
            return
        
        # 确认操作
        result = QMessageBox.question(
            self.view,
            "确认取消解锁",
            f"确定要取消解锁游戏 {app_id} 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 禁用按钮，防止重复操作
        self.view.enable_buttons(False)
        
        # 显示进度信息
        self.view.set_status(f"正在取消解锁游戏 {app_id}...")
        
        # 创建并显示进度对话框
        progress_dialog = QProgressDialog("正在取消解锁游戏...", "取消", 0, 100, self.view)
        progress_dialog.setWindowTitle("取消解锁进度")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        # 连接进度信号
        self.progressUpdated.connect(lambda msg, val: progress_dialog.setLabelText(msg))
        self.progressUpdated.connect(lambda msg, val: progress_dialog.setValue(val))
        
        async def remove_unlock_task():
            try:
                # 执行取消解锁操作
                success, message = await self.unlock_model.remove_unlock_async(
                    app_id,
                    lambda msg, val: self.progressUpdated.emit(msg, val)
                )
                
                # 更新游戏状态
                if success:
                    self.data_model.set_unlock_status(app_id, False, auto_save=True)
                
                # 发送完成信号
                self.unlockCompleted.emit(success, message, app_id)
            except Exception as e:
                # 发送错误信号
                self.unlockCompleted.emit(False, f"取消解锁过程中发生错误: {str(e)}", app_id)
        
        # 创建事件循环并在单独的线程中运行任务
        def run_async_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(remove_unlock_task())
        
        # 在单独的线程中运行事件循环
        thread = threading.Thread(target=run_async_task)
        thread.start()
    
    def update_game_name_silently(self, app_id, game_name, force=True):
        """静默更新游戏名称，不显示消息框
        
        Args:
            app_id: 游戏AppID
            game_name: 新的游戏名称
            force: 是否强制更新名称，即使游戏已有名称
        """
        game = self.data_model.get_game(app_id)
        if game and game_name:
            # 获取当前名称
            current_name = game.get("game_name", "")
            
            # 判断是否需要更新
            # 如果force=True，则强制更新
            # 否则只更新名称为空或默认名称的游戏
            if force or not current_name or current_name.startswith("Game "):
                # 获取数据库名称
                databases = game.get("databases", [])
                database_name = databases[0] if databases else "default"
                
                # 更新游戏名称 - 只传递需要更新的游戏名称
                self.data_model.update_game(
                    app_id=app_id,
                    database_name=database_name,
                    game_name=game_name,
                    auto_save=True
                )
                
                return True
        
        return False

    def update_progress(self, message: str, progress: int):
        """更新进度信息
        
        Args:
            message: 进度消息
            progress: 进度值(0-100)
        """
        self.progressUpdated.emit(message, progress)
    
    def handle_unlock_completed(self, success: bool, message: str, app_id: str):
        """处理解锁完成事件
        
        Args:
            success: 是否成功
            message: 消息
            app_id: 游戏AppID
        """
        # 启用按钮
        self.view.enable_buttons(True)
        
        # 更新表格
        games = self.data_model.get_all_games()
        self.view.update_table(games)
        
        # 显示消息
        if success:
            # 检查是否为取消解锁操作
            if "取消" in message:
                self.view.set_status(f"已取消解锁游戏 {app_id}")
                QMessageBox.information(
                    self.view,
                    "取消解锁成功",
                    f"已成功取消解锁游戏 {app_id}"
                )
            else:
                self.view.set_status(f"已解锁游戏 {app_id}")
                QMessageBox.information(
                    self.view,
                    "解锁成功",
                    f"已成功解锁游戏 {app_id}"
                )
        else:
            self.view.set_status(f"操作失败: {message}")
            QMessageBox.warning(
                self.view,
                "操作失败",
                message
            )
    
    def check_all_unlocked_games(self, show_dialog: bool = False):
        """检查所有游戏的解锁状态（在后台进行，不刷新UI，不显示弹窗）

        Args:
            show_dialog: 已废弃参数，仅保留兼容性，不再使用
        """
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            QMessageBox.warning(
                self.view,
                "配置错误",
                "配置无效，请先配置Steam路径和清单仓库路径。"
            )
            return

        # 显示初始状态
        self.view.set_status("正在后台检查解锁状态...")

        # 获取所有游戏
        all_games = self.data_model.get_all_games()
        if not all_games:
            self.view.set_status("没有游戏数据可检查")
            return

        # 创建协程函数
        async def check_unlock_status_task():
            try:
                # 扫描已解锁的游戏
                try:
                    self.view.set_status("正在后台扫描已解锁的游戏...")

                    unlocked_games = await self.unlock_model.scan_unlocked_games()

                except Exception as e:
                    self.view.set_status(f"扫描已解锁游戏时出错: {str(e)}")
                    return

                if not unlocked_games:
                    self.view.set_status("未发现任何已解锁的游戏")
                    return

                self.view.set_status("统计状态变化的游戏数量...")
                # 统计状态变化的游戏数量
                updated_count = 0
                total_games = len(all_games)
                processed_games = 0

                # 单独更新每个游戏的状态，但只保存一次
                for game in all_games:
                    processed_games += 1
                    app_id = game.get("app_id", "")
                    if not app_id:
                        continue

                    # 更新进度信息
                    progress_msg = f"正在检查游戏进度 ({processed_games}/{total_games})"
                    QTimer.singleShot(0, lambda msg=progress_msg: self.view.set_status(msg))

                    # 获取当前和新的解锁状态
                    current_status = game.get("is_unlocked", False)
                    new_status = app_id in unlocked_games

                    # 如果状态发生变化，更新它
                    if current_status != new_status:
                        self.data_model.set_unlock_status(app_id, new_status, auto_save=False)
                        updated_count += 1

                # 一次性保存所有更改
                if updated_count > 0:
                    try:
                        self.data_model.save_data(silent=True)
                    except Exception as e:
                        self.view.set_status(f"保存数据时出错: {str(e)}")
                        return

                # 更新状态栏，提示用户点击"刷新显示"按钮
                message = ""
                if updated_count > 0:
                    message = f"解锁状态检查完成，已更新{updated_count}个游戏的状态。请点击'刷新显示'按钮查看最新状态。"
                else:
                    message = "解锁状态检查完成，未发现状态变化。"

                # 在主线程更新UI
                self.view.set_status(message)

            except Exception as e:
                # 显示错误消息
                error_msg = f"检查解锁状态时出错: {str(e)}"
                QTimer.singleShot(0, lambda: self.view.set_status(error_msg))

        # 创建事件循环并在单独的线程中运行任务
        import threading

        def run_async_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(check_unlock_status_task())
            except Exception as e:
                QTimer.singleShot(0, lambda: self.view.set_status(f"运行异步任务时出错: {str(e)}"))
            finally:
                loop.close()

        # 在单独的线程中运行事件循环
        thread = threading.Thread(target=run_async_task)
        thread.daemon = True  # 设置为守护线程，应用退出时自动结束
        thread.start()

    def update_game_name_silently(self, app_id, game_name, force=True):
        """静默更新游戏名称，不显示消息框
        
        Args:
            app_id: 游戏AppID
            game_name: 新的游戏名称
            force: 是否强制更新名称，即使游戏已有名称
        """
        game = self.data_model.get_game(app_id)
        if game and game_name:
            # 获取当前名称
            current_name = game.get("game_name", "")
            
            # 判断是否需要更新
            # 如果force=True，则强制更新
            # 否则只更新名称为空或默认名称的游戏
            if force or not current_name or current_name.startswith("Game "):
                # 获取数据库名称
                databases = game.get("databases", [])
                database_name = databases[0] if databases else "default"
                
                # 更新游戏名称 - 只传递需要更新的游戏名称
                self.data_model.update_game(
                    app_id=app_id,
                    database_name=database_name,
                    game_name=game_name,
                    auto_save=True
                )
                
                return True
        
        return False 
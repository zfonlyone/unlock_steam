import os
import sys
import asyncio
from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QDialog, QProgressDialog, QInputDialog
from PyQt5.QtCore import QPoint, QObject, pyqtSignal, QTimer
from typing import List, Dict, Any, Optional, Tuple
from PyQt5.QtWidgets import QApplication
import threading
import time
import random


class UnlockController(QObject):
    """解锁功能控制器(Controller层)"""
    
    # 进度信号
    progressUpdated = pyqtSignal(str, int)  # 消息和进度百分比
    unlockCompleted = pyqtSignal(bool, str, str)  # 成功/失败, 消息, app_id
    toolCompleted = pyqtSignal(str, str, bool) # 工具名, 结果消息, 是否成功
    batchUnlockCompleted = pyqtSignal(int, int, int, float) # 成功, 失败, 总计, 耗时
    
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
        self.view.themeChanged.connect(self._on_theme_changed)
        self.view.syncRequested.connect(self.view.sync_games_to_table)
        
        # 连接本地处理信号
        self.toolCompleted.connect(self.handle_tool_completed)
        self.progressUpdated.connect(self.handle_progress_update)
        
        self._active_progress_dialog = None
        
        # 连接工具信号
        self.view.toolCheckAddAppIDRequested.connect(lambda: self.run_tool("check_addappid.py"))
        self.view.toolReplaceManifestRequested.connect(lambda: self.run_tool("replace_manifest.py"))
        self.view.toolEnableManifestRequested.connect(lambda: self.run_tool("enable_manifest.py"))
        self.view.toolFindNoManifestRequested.connect(lambda: self.run_tool("find_no_manifest.py"))
        self.view.toolCleanInvalidLuaRequested.connect(lambda: self.run_tool("clean_invalid_lua.py"))
        self.view.toolFixFormatsRequested.connect(lambda: self.run_tool("fix_lua_formats.py"))
        self.view.fetchAllDlcRequested.connect(self.fetch_all_dlc)
        self.view.completeAllManifestsRequested.connect(self.complete_all_manifests)
        self.view.batchUnlockLiteRequested.connect(self.batch_unlock_lite)
        
        # 连接菜单动作信号
        # 连接菜单动作信号
        self.view.updateManifestRequested.connect(self.update_manifest_via_api)
        self.view.toggleUnlockRequested.connect(self.toggle_unlock_state)
        
        # 应用初始主题
        initial_theme = self.config_model.get("theme", "dark")
        self.view.set_theme(initial_theme)
        
        # 确保 tools 目录加载正确
        self._ensure_tools_path()

    def _ensure_tools_path(self):
        """确保 tools 目录在 sys.path 中"""
        import sys
        if getattr(sys, 'frozen', False):
            tools_dir = os.path.join(sys._MEIPASS, "tools")
        else:
            tools_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
        
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)

    def _on_theme_changed(self, theme_name: str):
        """处理主题切换并持久化"""
        self.config_model.set("theme", theme_name)
        self.config_model.save_config()
    
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
        
        # 创建并显示进度对话框 (在主线程)
        self._active_progress_dialog = QProgressDialog(f"正在解锁游戏 {app_id}...", "取消", 0, 100, self.view)
        self._active_progress_dialog.setWindowTitle("解锁进度")
        self._active_progress_dialog.setMinimumDuration(0)
        self._active_progress_dialog.setValue(10)
        self._active_progress_dialog.show()
        
        # 定义本地进度回调函数 - 仅发送信号
        def update_progress(msg, val):
            self.progressUpdated.emit(msg, val)
        
        # 创建事件循环
        async def unlock_task():
            try:
                # 执行解锁操作
                success, message = await self.unlock_model.unlock_game_async(
                    app_id, 
                    database_name,
                    update_progress
                )
                
                # 确保进度条完成
                update_progress(f"操作完成: {message}", 100)
                
                # 更新游戏状态
                if success:
                    self.data_model.set_unlock_status(app_id, True, auto_save=True)
                
                # 发送完成信号
                self.unlockCompleted.emit(success, message, app_id)
            except Exception as e:
                # 发送错误信号
                error_msg = f"解锁过程中发生错误: {str(e)}"
                print(error_msg)
                update_progress(error_msg, 100)
                self.unlockCompleted.emit(False, error_msg, app_id)
                
        # 创建事件循环并在单独的线程中运行任务
        def run_async_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(unlock_task())
                loop.close()
            except Exception as e:
                print(f"解锁任务线程出错: {e}")
                QTimer.singleShot(0, lambda: self.view.set_status(f"解锁任务出错: {e}"))
        
        # 在单独的线程中运行事件循环
        thread = threading.Thread(target=run_async_task)
        thread.daemon = True
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
        self._active_progress_dialog = QProgressDialog(f"正在取消解锁游戏 {app_id}...", "取消", 0, 100, self.view)
        self._active_progress_dialog.setWindowTitle("取消解锁进度")
        self._active_progress_dialog.setMinimumDuration(0)
        self._active_progress_dialog.setValue(10)
        self._active_progress_dialog.show()
        
        # 定义本地进度回调函数
        def update_progress(msg, val):
            self.progressUpdated.emit(msg, val)
        
        async def remove_unlock_task():
            try:
                # 执行取消解锁操作
                success, message = await self.unlock_model.remove_unlock_async(
                    app_id,
                    update_progress
                )
                
                # 确保进度条完成
                update_progress(f"操作完成: {message}", 100)
                
                # 更新游戏状态
                if success:
                    self.data_model.set_unlock_status(app_id, False, auto_save=True)
                
                # 发送完成信号
                self.unlockCompleted.emit(success, message, app_id)
            except Exception as e:
                # 发送错误信号
                error_msg = f"取消解锁过程中发生错误: {str(e)}"
                print(error_msg)
                update_progress(error_msg, 100)
                self.unlockCompleted.emit(False, error_msg, app_id)
        
        # 创建事件循环并在单独的线程中运行任务
        def run_async_task():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(remove_unlock_task())
                loop.close()
            except Exception as e:
                print(f"取消解锁任务线程出错: {e}")
                QTimer.singleShot(0, lambda: self.view.set_status(f"取消解锁任务出错: {e}"))
        
        # 在单独的线程中运行事件循环
        thread = threading.Thread(target=run_async_task)
        thread.daemon = True
        thread.start()
    
    def unlock_game_internal(self, app_id: str) -> Tuple[bool, str]:
        """解锁游戏的内部方法，不显示UI，适用于批量操作
        
        Args:
            app_id: 游戏AppID
            
        Returns:
            (是否成功, 消息)
        """
        # 获取游戏信息
        game = self.data_model.get_game(app_id)
        if not game:
            return False, f"找不到游戏 {app_id} 的信息"
        
        # 获取数据库列表
        databases = game.get("databases", [])
        database_name = databases[0] if databases else "default"
        
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 定义进度回调函数
            def progress_callback(msg, val):
                print(f"解锁游戏 {app_id} 进度: {msg} ({val}%)")
            
            # 使用 unlock_game_async，它有完整的三级回退机制：
            # 1. 本地仓库 2. 远程下载 3. 基础解锁
            print(f"开始解锁游戏 {app_id}...")
            success, message = loop.run_until_complete(
                self.unlock_model.unlock_game_async(app_id, database_name, progress_callback)
            )
            
            # 关闭事件循环
            loop.close()
            
            # 更新游戏状态
            if success:
                self.data_model.set_unlock_status(app_id, True, auto_save=True)
                print(f"游戏 {app_id} 解锁成功")
            else:
                print(f"游戏 {app_id} 解锁失败: {message}")
            
            return success, message
        
        except Exception as e:
            error_msg = f"解锁游戏 {app_id} 时出错: {str(e)}"
            print(error_msg)
            import traceback
            traceback.print_exc()
            return False, error_msg

    
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

    def handle_progress_update(self, message: str, progress: int):
        """处理进度更新信号 (在主线程执行)"""
        try:
            if self._active_progress_dialog and self._active_progress_dialog.isVisible():
                self._active_progress_dialog.setLabelText(message)
                if progress >= 0:
                    self._active_progress_dialog.setValue(progress)
            
            # 同时更新状态栏
            self.view.set_status(message)
        except Exception as e:
            print(f"处理进度信号出错: {e}")

    def update_progress(self, message: str, progress: int):
        """外部调用的更新进度方法"""
        self.progressUpdated.emit(message, progress)
    
    def handle_unlock_completed(self, success: bool, message: str, app_id: str):
        """处理解锁完成事件"""
        # 关闭进度对话框
        if self._active_progress_dialog:
            self._active_progress_dialog.close()
            self._active_progress_dialog = None

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

        # 获取所有游戏 (可能为空，但不影响扫描本地已解锁的项目)
        all_games = self.data_model.get_all_games()
        
        # 创建 AppID 到名称的映射，以便增量扫描时保留已有名称
        known_names = {str(g.get("app_id")): g.get("game_name") for g in all_games if g.get("game_name")}

        # 创建协程函数
        async def check_unlock_status_task():
            try:
                # 扫描已解锁的游戏
                try:
                    self.view.set_status("正在启动增量扫描...")
                    
                    # 定义扫描进度回调
                    def scan_progress(msg):
                        self.progressUpdated.emit(msg, -1)
                    
                    # 增量填充回调：每扫描到一批直接在界面显示
                    def scan_batch(app_ids):
                        batch_games = []
                        for aid in app_ids:
                            aid_str = str(aid)
                            g_data = {"app_id": aid_str, "is_unlocked": True}
                            # 只有当该 AppID 不在已知数据库中且没有名称时，才提供占位符
                            if aid_str not in known_names:
                                g_data["game_name"] = f"发现已解锁 {aid_str}"
                            batch_games.append(g_data)
                        self.view.syncRequested.emit(batch_games)

                    # 1. 扫描前：首先将全量列表填入界面 (Model 此时通过本地数据库刷新)
                    self.view.update_table(all_games)
                    
                    # 2. 开始扫描：传入增量回调
                    unlocked_games = await self.unlock_model.scan_unlocked_games(
                        progress_callback=scan_progress,
                        batch_callback=scan_batch
                    )

                except Exception as e:
                    self.view.set_status(f"扫描出错: {str(e)}")
                    return

                if not unlocked_games:
                    self.view.set_status("未发现任何解锁项")
                    return

                # --- 静默后台同步数据库 ---
                # 界面已经通过 batch_callback 和 all_games 预填充刷新了
                # 这里只需要计算差异并更新 DB
                existing_app_ids = {game.get("app_id") for game in all_games if game.get("app_id")}
                db_updates = []
                new_app_ids = []
                
                for game in all_games:
                    app_id = game.get("app_id", "")
                    new_status = app_id in unlocked_games
                    if game.get("is_unlocked") != new_status:
                        db_updates.append((app_id, new_status))
                
                for app_id in unlocked_games:
                    if app_id not in existing_app_ids:
                        new_app_ids.append(app_id)
                
                if db_updates:
                    self.data_model.batch_set_unlock_status(db_updates)
                if new_app_ids:
                    self.data_model.batch_add_unlocked_games(new_app_ids)

                self.view.set_status(f"扫描完毕！数据库同步完成 (更新 {len(db_updates)}，新增 {len(new_app_ids)})")

            except Exception as e:
                # 显示错误消息
                error_msg = f"检查解锁状态时出错: {str(e)}"
                print(f"ERROR in check_unlock_status_task: {e}")
                import traceback
                traceback.print_exc()
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

    def run_tool(self, script_name: str, target_path: str = None):
        """运行 tools 目录下的工具
        
        直接导入并调用工具函数，无需 subprocess
        
        Args:
            script_name: 脚本文件名
            target_path: 目标路径（文件或目录），默认为插件目录
        """
        import sys
        
        # 如果没有指定目标，默认使用插件目录
        if not target_path:
            steam_path = self.unlock_model.get_steam_path()
            target_path = str(steam_path / "config" / "stplug-in")
        
        self.view.set_status(f"正在运行工具 {script_name}...")
        
        # 工具名到函数的映射
        tool_mapping = {
            "check_addappid.py": ("check_addappid", "run_check"),
            "replace_manifest.py": ("replace_manifest", "run_replace"),
            "enable_manifest.py": ("enable_manifest", "run_enable"),
            "find_no_manifest.py": ("find_no_manifest", "run_find"),
            "clean_invalid_lua.py": ("clean_invalid_lua", "run_clean"),
            "fix_lua_formats.py": ("fix_lua_formats", "run_fix_formats"),
        }
        
        if script_name not in tool_mapping:
            QMessageBox.critical(self.view, "错误", f"未知的工具脚本: {script_name}")
            return
        
        module_name, func_name = tool_mapping[script_name]
        
        def run():
            try:
                # 添加 tools 目录到 Python 路径
                if getattr(sys, 'frozen', False):
                    tools_dir = os.path.join(sys._MEIPASS, "tools")
                else:
                    tools_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools")
                
                if tools_dir not in sys.path:
                    sys.path.insert(0, tools_dir)
                
                # 动态导入模块
                module = __import__(module_name)
                func = getattr(module, func_name)
                
                # 定义进度回调
                def progress_callback(msg):
                    QTimer.singleShot(0, lambda m=msg: self.view.set_status(f"[{script_name}] {m}"))
                
                # 执行工具函数
                QTimer.singleShot(0, lambda: self.view.set_status(f"[{script_name}] 正在执行..."))
                
                # 特殊处理不同工具
                if func_name == "run_clean":
                    # 清理无效 Lua（自动删除）
                    result = func(target_path, auto_delete=True, progress_callback=progress_callback)
                elif func_name == "run_check":
                    # 检查 Lua 脚本，发现问题时询问是否修复
                    result = func(target_path, progress_callback=progress_callback)
                    
                    if result.get("problems"):
                        # 有问题，询问是否修复
                        problem_count = len(result["problems"])
                        msg = f"发现 {problem_count} 个文件有非法字符\n\n是否自动修复？"
                        
                        def ask_fix():
                            reply = QMessageBox.question(
                                self.view, 
                                "发现问题",
                                msg,
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.Yes
                            )
                            if reply == QMessageBox.Yes:
                                # 执行修复
                                threading.Thread(
                                    target=self._run_fix_tool, 
                                    args=(module, target_path, progress_callback, script_name),
                                    daemon=True
                                ).start()
                            else:
                                # 用户拒绝修复，但依然显示扫描结果
                                self.view.refreshDisplayRequested.emit()
                                QMessageBox.information(self.view, "扫描完成", f"扫描完成，共发现 {problem_count} 个待修复问题。")
                        
                        QTimer.singleShot(0, ask_fix)
                        return  # 进入修复流程，由修复流程负责最终反馈
                else:
                    result = func(target_path, progress_callback=progress_callback)
                
                # 显示结果
                message = result.get("message", "完成")
                self.toolCompleted.emit(script_name, message, True)
                
            except Exception as e:
                error_msg = f"工具运行异常: {str(e)}"
                import traceback
                traceback.print_exc()
                self.toolCompleted.emit(script_name, error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()
    
    def _run_fix_tool(self, module, target_path, progress_callback, script_name):
        """执行修复工具"""
        try:
            fix_func = getattr(module, "run_fix")
            result = fix_func(target_path, progress_callback=progress_callback)
            message = result.get("message", "修复完成")
            self.toolCompleted.emit(f"{script_name} [修复]", message, True)
        except Exception as e:
            error_msg = f"修复异常: {str(e)}"
            import traceback
            traceback.print_exc()
            self.toolCompleted.emit(f"{script_name} [修复]", error_msg, False)

    def handle_tool_completed(self, script_name: str, message: str, is_success: bool):
        """处理工具运行完成的 UI 反馈 (在主线程执行)"""
        self.view.set_status(f"[{script_name}] {'已完成' if is_success else '运行失败'}")
        
        if is_success:
            QMessageBox.information(self.view, "工具结果", f"工具 [{script_name}] 运行成功:\n\n{message}")
        else:
            QMessageBox.critical(self.view, "工具错误", f"工具 [{script_name}] 运行过程中出错:\n\n{message}")
        
        # 无论成败，自动刷新 UI 列表，展示可能的变化
        self.view.refreshDisplayRequested.emit()





    def toggle_single_manifest(self, app_id: str, enable: bool):
        """对单个游戏进行清单禁用/启用操作"""
        steam_path = self.unlock_model.get_steam_path()
        lua_file = steam_path / "config" / "stplug-in" / f"{app_id}.lua"
        
        # 如果主目录找不到，尝试在备份目录找
        if not lua_file.exists():
            lua_file = steam_path / "config" / "stplug-in-bak" / f"{app_id}.lua"
            
        if not lua_file.exists():
            QMessageBox.warning(self.view, "提示", f"找不到游戏 {app_id} 的脚本文件 (stplug-in 或 stplug-in-bak)。")
            return
            
        script = "enable_manifest.py" if enable else "replace_manifest.py"
        self.run_tool(script, str(lua_file))

    def toggle_unlock_state(self, game_data: dict):
        """切换禁用/启用状态"""
        app_id = game_data.get("app_id")
        is_unlocked = game_data.get("is_unlocked")
        
        async def do_toggle():
            if is_unlocked == "disabled":
                success, msg = await self.unlock_model.enable_unlock(app_id)
            else:
                success, msg = await self.unlock_model.disable_unlock(app_id)
            
            if success:
                # 刷新状态
                new_status = True if is_unlocked == "disabled" else "disabled"
                self.data_model.set_unlock_status(app_id, new_status, auto_save=True)
                # 重新扫描一次确保 UI 同步
                QTimer.singleShot(0, self.check_all_unlocked_games)
            else:
                QTimer.singleShot(0, lambda: QMessageBox.warning(self.view, "操作失败", msg))

        def run_it():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(do_toggle())
            loop.close()

        threading.Thread(target=run_it, daemon=True).start()

    def update_manifest_via_api(self, game_data: dict):
        """通过 API 更新清单"""
        app_id = str(game_data.get("app_id"))
        api_key = self.config_model.get("api_key", "")
        
        if not api_key:
            QMessageBox.warning(self.view, "提示", "请先在设置中配置 ManifestHub API 密钥")
            return

        self.view.set_status(f"正在通过 API 获取 {app_id} 的最新清单...")
        
        async def fetch():
            try:
                from models import ManifestHub_API_model
                api = ManifestHub_API_model.get_api(api_key)
                
                # 1. 获取游戏关联的清单信息 (可以从 API 获取 JSON)
                game_json = api.get_game_json_from_github(app_id)
                if not game_json:
                    QTimer.singleShot(0, lambda: self.view.set_status(f"未在 ManifestHub 找到 {app_id}"))
                    return
                
                # 简单实现：告知用户已找到信息
                QTimer.singleShot(0, lambda: QMessageBox.information(self.view, "更新清单", f"已从 API 同步游戏 {app_id} 的信息"))
                self.view.set_status(f"已更新 {app_id} 的元数据")
            except Exception as e:
                QTimer.singleShot(0, lambda: self.view.set_status(f"更新清单失败: {e}"))

        threading.Thread(target=lambda: asyncio.run(fetch()), daemon=True).start()

    def fetch_and_add_dlc(self, app_id: str):
        """获取单个游戏的 DLC 并添加到 Lua 文件
        
        Args:
            app_id: 游戏 App ID
        """
        steam_path = self.unlock_model.get_steam_path()
        lua_dir = str(steam_path / "config" / "stplug-in")
        
        self.view.set_status(f"正在获取游戏 {app_id} 的 DLC 列表...")
        
        def run():
            try:
                from fetch_dlc import run_fetch_single
                
                def progress_callback(msg):
                    QTimer.singleShot(0, lambda m=msg: self.view.set_status(f"[DLC] {m}"))
                
                result = run_fetch_single(app_id, lua_dir, progress_callback)
                
                # 显示结果
                message = result.get("message", "完成")
                self.toolCompleted.emit(f"获取DLC ({app_id})", message, result.get("success", False))
                
            except Exception as e:
                error_msg = f"获取 DLC 失败: {str(e)}"
                import traceback
                traceback.print_exc()
                self.toolCompleted.emit(f"获取DLC ({app_id})", error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()

    def fetch_all_dlc(self):
        """批量获取所有游戏的 DLC 并添加到 Lua 文件"""
        steam_path = self.unlock_model.get_steam_path()
        lua_dir = str(steam_path / "config" / "stplug-in")
        
        # 确认操作
        result = QMessageBox.question(
            self.view,
            "一键获取所有 DLC",
            "将为所有已解锁的游戏获取 DLC 列表并添加到 Lua 文件。\n\n"
            "这可能需要一些时间，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        self.view.set_status("正在批量获取所有游戏的 DLC...")
        
        def run():
            try:
                from fetch_dlc import run_fetch_all
                
                def progress_callback(msg):
                    QTimer.singleShot(0, lambda m=msg: self.view.set_status(f"[批量DLC] {m}"))
                
                result = run_fetch_all(lua_dir, progress_callback)
                
                # 显示结果
                message = result.get("message", "完成")
                self.toolCompleted.emit("批量获取DLC", message, result.get("success", False))
                
            except Exception as e:
                error_msg = f"批量获取 DLC 失败: {str(e)}"
                import traceback
                traceback.print_exc()
                self.toolCompleted.emit("批量获取DLC", error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()

    def complete_manifests(self, app_id: str):
        """补全单个游戏的清单
        
        Args:
            app_id: 游戏 App ID
        """
        steam_path = self.unlock_model.get_steam_path()
        lua_dir = str(steam_path / "config" / "stplug-in")
        depot_cache = str(steam_path / "config" / "depotcache")
        
        self.view.set_status(f"正在补全游戏 {app_id} 的清单...")
        
        def run():
            try:
                from complete_manifests import run_complete_single
                
                def progress_callback(msg):
                    QTimer.singleShot(0, lambda m=msg: self.view.set_status(f"[清单] {m}"))
                
                result = run_complete_single(app_id, lua_dir, depot_cache, progress_callback)
                
                message = result.get("message", "完成")
                self.toolCompleted.emit(f"补全清单 ({app_id})", message, result.get("success", False))
                
            except Exception as e:
                error_msg = f"补全清单失败: {str(e)}"
                import traceback
                traceback.print_exc()
                self.toolCompleted.emit(f"补全清单 ({app_id})", error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()

    def complete_all_manifests(self):
        """批量补全所有游戏的清单"""
        steam_path = self.unlock_model.get_steam_path()
        lua_dir = str(steam_path / "config" / "stplug-in")
        depot_cache = str(steam_path / "config" / "depotcache")
        
        # 确认操作
        result = QMessageBox.question(
            self.view,
            "一键补全清单",
            "将为所有已解锁的游戏补全缺失的 DLC 清单文件。\n\n"
            "这可能需要较长时间，是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        self.view.set_status("正在批量补全所有游戏的清单...")
        
        def run():
            try:
                from complete_manifests import run_complete_all
                
                def progress_callback(msg):
                    QTimer.singleShot(0, lambda m=msg: self.view.set_status(f"[批量清单] {m}"))
                
                result = run_complete_all(lua_dir, depot_cache, progress_callback)
                
                message = result.get("message", "完成")
                self.toolCompleted.emit("批量补全清单", message, result.get("success", False))
                
            except Exception as e:
                error_msg = f"批量补全清单失败: {str(e)}"
                import traceback
                traceback.print_exc()
                self.toolCompleted.emit("批量补全清单", error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()

    def batch_unlock_lite(self):
        """批量解锁Lite - 仅下载Lua文件，不下载清单"""
        # 确认操作
        result = QMessageBox.question(
            self.view,
            "一键解锁 Lite",
            "将批量解锁所有搜索结果中的游戏。\n\n"
            "Lite 模式仅下载 Lua 脚本，不下载清单文件。\n"
            "适用于快速解锁或网络较慢的情况。\n\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 获取所有未解锁的游戏
        unlocked_ids = set()
        for row in range(self.game_model.rowCount()):
            game = self.game_model.get_game(row)
            if game and not game.get("is_unlocked"):
                unlocked_ids.add(game.get("app_id"))
        
        if not unlocked_ids:
            QMessageBox.information(self.view, "提示", "没有需要解锁的游戏")
            return
        
        self.view.set_status(f"正在批量解锁 Lite ({len(unlocked_ids)} 个游戏)...")
        
        def run():
            import urllib.request
            import urllib.error
            import json
            
            steam_path = self.unlock_model.get_steam_path()
            st_path = steam_path / "config" / "stplug-in"
            st_path.mkdir(exist_ok=True)
            
            repo_path = "SteamAutoCracks/ManifestHub"
            success_count = 0
            fail_count = 0
            
            for i, app_id in enumerate(unlocked_ids):
                try:
                    QTimer.singleShot(0, lambda a=app_id, n=i: self.view.set_status(
                        f"[Lite] {n+1}/{len(unlocked_ids)} 正在处理 {a}..."))
                    
                    # 只下载 Lua 文件
                    lua_url = f"https://raw.githubusercontent.com/{repo_path}/{app_id}/{app_id}.lua"
                    lua_path = st_path / f"{app_id}.lua"
                    
                    req = urllib.request.Request(lua_url, headers={"User-Agent": "SteamUnlocker/2.3"})
                    with urllib.request.urlopen(req, timeout=30) as response:
                        content = response.read()
                        with open(str(lua_path), 'wb') as f:
                            f.write(content)
                        success_count += 1
                        
                except Exception as e:
                    fail_count += 1
                    print(f"Lite 解锁 {app_id} 失败: {e}")
            
            message = f"Lite 解锁完成！成功 {success_count} 个，失败 {fail_count} 个"
            self.toolCompleted.emit("批量解锁 Lite", message, success_count > 0)
        
        threading.Thread(target=run, daemon=True).start()

    def update_lua_from_remote(self, app_id: str):
        """从远程更新单个游戏的 Lua 文件"""
        self.view.set_status(f"正在更新 {app_id} 的 Lua 文件...")
        
        def run():
            import urllib.request
            import urllib.error
            
            try:
                steam_path = self.unlock_model.get_steam_path()
                st_path = steam_path / "config" / "stplug-in"
                st_path.mkdir(exist_ok=True)
                
                repo_path = "SteamAutoCracks/ManifestHub"
                lua_url = f"https://raw.githubusercontent.com/{repo_path}/{app_id}/{app_id}.lua"
                lua_path = st_path / f"{app_id}.lua"
                
                req = urllib.request.Request(lua_url, headers={"User-Agent": "SteamUnlocker/2.3"})
                with urllib.request.urlopen(req, timeout=30) as response:
                    content = response.read()
                    with open(str(lua_path), 'wb') as f:
                        f.write(content)
                
                self.toolCompleted.emit(f"更新Lua ({app_id})", f"成功更新 {app_id}.lua", True)
                
            except Exception as e:
                error_msg = f"更新 Lua 失败: {str(e)}"
                self.toolCompleted.emit(f"更新Lua ({app_id})", error_msg, False)
        
        threading.Thread(target=run, daemon=True).start()
 
import asyncio
from PyQt5.QtWidgets import QMenu, QAction, QMessageBox, QDialog, QProgressDialog, QInputDialog
from PyQt5.QtCore import QPoint, QObject, pyqtSignal, QTimer
from typing import List, Dict, Any, Optional
from PyQt5.QtWidgets import QApplication

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
        
        # 连接视图信号到控制器方法
        self.view.contextMenuRequested.connect(self.show_context_menu)
        self.view.checkUnlockStatusRequested.connect(self.check_all_unlocked_games)
        self.view.fetchGameNamesRequested.connect(self.fetch_all_game_names)  # 连接获取游戏名称信号
        
        # 连接控制器信号到视图更新方法
        self.progressUpdated.connect(self.update_progress)
        self.unlockCompleted.connect(self.handle_unlock_completed)
    
    def show_context_menu(self, position: QPoint, game_data: dict):
        """显示右键菜单
        
        Args:
            position: 菜单位置
            game_data: 游戏数据字典，包含app_id和game_name
        """
        # 创建菜单
        menu = QMenu()
        
        # 获取游戏AppID
        app_id = game_data.get("app_id", "")
        if not app_id:
            return
        
        # 检查是否有游戏名称
        game_name = game_data.get("game_name", f"Game {app_id}")
        
        # 避免重复查询数据库，直接使用传入的游戏数据
        # 只检查解锁状态
        is_unlocked = False
        game = self.data_model.get_game(app_id)
        if game:
            is_unlocked = game.get("is_unlocked", False)
        
        # 根据解锁状态添加不同的菜单项
        if is_unlocked:
            remove_action = QAction("移除解锁", self.view)
            remove_action.triggered.connect(lambda: self.remove_unlock(app_id))
            menu.addAction(remove_action)
        else:
            unlock_action = QAction("解锁游戏", self.view)
            unlock_action.triggered.connect(lambda: self.unlock_game(app_id))
            menu.addAction(unlock_action)
        
        # 添加其他通用菜单项
        menu.addSeparator()
        
        # 运行游戏
        run_game_action = QAction("运行游戏", self.view)
        run_game_action.triggered.connect(lambda: self.run_game(app_id))
        menu.addAction(run_game_action)
        
        # 获取游戏名称
        get_name_action = QAction("获取游戏名称", self.view)
        get_name_action.triggered.connect(lambda: self.fetch_game_name(app_id))
        menu.addAction(get_name_action)
        
        # 打开Steam商店页面
        open_store_action = QAction("打开Steam页面", self.view)
        open_store_action.triggered.connect(lambda: self.open_steam_store(app_id))
        menu.addAction(open_store_action)
        
        # 显示菜单
        menu.exec_(position)
    
    def unlock_game(self, app_id: str):
        """解锁游戏
        
        Args:
            app_id: 游戏AppID
        """
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            QMessageBox.warning(
                self.view, 
                "配置错误", 
                "配置无效，请先配置Steam路径和清单仓库路径。"
            )
            return
        
        # 获取游戏信息
        game = self.data_model.get_game(app_id)
        if not game:
            QMessageBox.warning(
                self.view, 
                "错误", 
                f"未找到游戏 {app_id} 的数据"
            )
            return
        
        # 获取游戏数据库列表
        databases = game.get("databases", [])
        
        # 如果只有一个数据库，直接使用
        if len(databases) == 1:
            self.start_unlock_process(app_id, databases[0])
        # 如果有多个数据库，显示选择对话框
        elif len(databases) > 1:
            # 这里应该展示选择对话框，但由于我们还没有实现这个对话框，暂时使用第一个数据库
            # 在完整实现中，应该创建一个数据库选择对话框
            self.start_unlock_process(app_id, databases[0])
        else:
            QMessageBox.warning(
                self.view, 
                "错误", 
                f"游戏 {app_id} 没有关联的数据库"
            )
    
    def start_unlock_process(self, app_id: str, database_name: str):
        """开始解锁游戏
        
        Args:
            app_id: 游戏AppID
            database_name: 数据库名称
        """
        # 禁用按钮，避免重复操作
        self.view.enable_buttons(False)
        
        # 显示进度信息
        self.view.set_status(f"正在解锁游戏 {app_id}...")
        
        # 创建协程函数
        async def unlock_task():
            try:
                # 发送进度信号
                self.progressUpdated.emit(f"准备解锁游戏 {app_id}...", 10)
                
                # 调用解锁模型执行解锁操作
                success, message = await self.unlock_model.unlock_game(app_id, database_name)
                
                # 发送完成信号
                self.unlockCompleted.emit(success, message, app_id)
                
            except Exception as e:
                # 发送错误信号
                self.unlockCompleted.emit(False, str(e), app_id)
        
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 异步执行解锁任务
        def run_async_task():
            loop.run_until_complete(unlock_task())
            loop.close()
        
        # 在单独的线程中运行事件循环
        import threading
        thread = threading.Thread(target=run_async_task)
        thread.start()
    
    def remove_unlock(self, app_id: str):
        """移除游戏解锁
        
        Args:
            app_id: 游戏AppID
        """
        # 确认对话框
        result = QMessageBox.question(
            self.view,
            "确认移除",
            f"确定要移除游戏 {app_id} 的解锁吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 禁用按钮，避免重复操作
        self.view.enable_buttons(False)
        
        # 显示进度信息
        self.view.set_status(f"正在移除游戏 {app_id} 的解锁...")
        
        # 创建协程函数
        async def remove_unlock_task():
            try:
                # 调用解锁模型执行移除操作
                success, message = await self.unlock_model.remove_unlock(app_id)
                
                # 更新游戏状态
                if success:
                    self.data_model.set_unlock_status(app_id, False, auto_save=True)
                    
                # 刷新显示
                games = self.data_model.get_all_games()
                self.view.update_table(games)
                
                # 显示结果消息
                self.view.set_status(message)
                
            except Exception as e:
                # 显示错误消息
                self.view.set_status(f"移除解锁时出错: {str(e)}")
            finally:
                # 启用按钮
                self.view.enable_buttons(True)
        
        # 创建事件循环
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # 异步执行移除任务
        def run_async_task():
            loop.run_until_complete(remove_unlock_task())
            loop.close()
        
        # 在单独的线程中运行事件循环
        import threading
        thread = threading.Thread(target=run_async_task)
        thread.start()
    
    def run_game(self, app_id: str):
        """运行游戏
        
        Args:
            app_id: 游戏AppID
        """
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            QMessageBox.warning(
                self.view, 
                "配置错误", 
                "配置无效，请先配置Steam路径和清单仓库路径。"
            )
            return
            
        steam_path = self.config_model.get("steam_path", "")
        
        try:
            import subprocess
            import platform
            
            # 获取操作系统类型
            system = platform.system()
            
            # 使用Steam URL协议启动游戏
            if system == "Windows":
                subprocess.Popen(f'start steam://rungameid/{app_id}', shell=True)
            elif system == "Darwin":  # macOS
                subprocess.Popen(['open', f'steam://rungameid/{app_id}'])
            else:  # Linux 和其他系统
                subprocess.Popen(['xdg-open', f'steam://rungameid/{app_id}'])
                
            self.view.set_status(f"已发送启动请求: 游戏 {app_id}")
            
        except Exception as e:
            QMessageBox.critical(
                self.view,
                "启动失败",
                f"启动游戏失败: {str(e)}"
            )
    
    def fetch_game_name(self, app_id: str, force: bool = True):
        """获取游戏名称
        
        Args:
            app_id: 游戏AppID
            force: 是否强制更新名称，即使游戏已有名称
        """
        # 显示进度信息
        self.view.set_status(f"正在获取游戏 {app_id} 的名称...")
        
        # 使用Steam API获取游戏名称
        import requests
        import threading
        import time
        
        def fetch_name_task():
            # 定义多个可能的API和网页源
            sources = [
                # Steam官方API
                {
                    "name": "Steam API",
                    "type": "api",
                    "url": f"https://store.steampowered.com/api/appdetails?appids={app_id}",
                    "timeout": 10,  # 10秒超时
                    "extract": lambda data: data.get(str(app_id), {}).get('data', {}).get('name', None) 
                    if data.get(str(app_id), {}).get('success', False) else None
                },
                # SteamSpy API (备用)
                {
                    "name": "SteamSpy API",
                    "type": "api",
                    "url": f"https://steamspy.com/api.php?request=appdetails&appid={app_id}",
                    "timeout": 5,
                    "extract": lambda data: data.get('name', None)
                }
            ]
            
            # 尝试每个来源
            last_error = None
            
            for source in sources:
                try:
                    # 添加延迟，避免请求过快
                    time.sleep(0.5)
                    
                    # 显示尝试信息
                    QTimer.singleShot(0, lambda: self.view.set_status(f"正在从 {source['name']} 获取游戏 {app_id} 的名称..."))
                    
                    # 进行网络请求
                    response = requests.get(source['url'], timeout=source['timeout'])
                    
                    # 检查HTTP错误
                    response.raise_for_status()
                    
                    if source['type'] == 'api':
                        # 解析JSON数据
                        data = response.json()
                        
                        # 提取游戏名称
                        game_name = source['extract'](data)
                        
                        if game_name:
                            # 在主线程中更新UI，传递force参数
                            QTimer.singleShot(0, lambda: self.handle_fetch_name_completed(app_id, game_name, force=force))
                            return
                        
                except requests.exceptions.RequestException as e:
                    # 记录错误，但继续尝试下一个来源
                    last_error = e
                    continue
                except Exception as e:
                    # 记录错误，但继续尝试下一个来源
                    last_error = e
                    continue
            
            # 如果所有来源都失败
            if last_error:
                error_msg = f"所有获取方式都失败，最后一个错误: {str(last_error)}"
                QTimer.singleShot(0, lambda: self.handle_fetch_name_completed(app_id, None, error_message=error_msg, force=force))
            else:
                error_msg = f"无法获取游戏 {app_id} 的名称，请检查游戏ID是否正确或稍后再试"
                QTimer.singleShot(0, lambda: self.handle_fetch_name_completed(app_id, None, error_message=error_msg, force=force))
        
        # 在后台线程中执行网络请求，避免UI阻塞
        thread = threading.Thread(target=fetch_name_task)
        thread.daemon = True
        thread.start()
    
    def handle_fetch_name_completed(self, app_id: str, game_name: str = None, error_message: str = None, force: bool = False):
        """处理游戏名称获取完成事件
        
        Args:
            app_id: 游戏AppID
            game_name: 获取到的游戏名称，如果失败则为None
            error_message: 错误信息，如果成功则为None
            force: 是否强制更新名称
        """
        if error_message:
            # 显示错误消息
            result = QMessageBox.warning(
                self.view,
                "获取游戏名称失败",
                f"{error_message}\n\n是否要手动输入游戏名称?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            # 如果用户选择手动输入
            if result == QMessageBox.Yes:
                # 显示输入对话框
                text, ok = QInputDialog.getText(
                    self.view, 
                    "手动输入", 
                    f"请输入游戏 {app_id} 的名称:",
                    text=f"Game {app_id}"
                )
                
                # 如果用户点击了确定并输入了内容
                if ok and text:
                    game_name = text
                else:
                    self.view.set_status(f"获取游戏 {app_id} 名称已取消")
                    return
            else:
                self.view.set_status(f"获取游戏 {app_id} 名称失败")
                return
            
        # 更新游戏名称
        game = self.data_model.get_game(app_id)
        if game and game_name:
            databases = game.get("databases", [])
            database_name = databases[0] if databases else ""
            
            # 检查是否需要更新（空名称或force=True）
            current_name = game.get("game_name", "")
            if force or not current_name:
                # 更新游戏名称并保存数据
                self.data_model.update_game(
                    app_id,
                    database_name,
                    game_name,
                    game.get("is_unlocked", False),
                    auto_save=True  # 确保保存到文件
                )
                
                # 显示成功消息
                if force and current_name:
                    QMessageBox.information(
                        self.view,
                        "名称已更新",
                        f"游戏 {app_id} 的名称已从\n'{current_name}'\n更新为\n'{game_name}'"
                    )
                
                # 刷新表格
                games = self.data_model.get_all_games()
                self.view.update_table(games)
                
                # 更新状态栏
                self.view.set_status(f"游戏 {app_id} 的名称已更新为 '{game_name}'")
            else:
                self.view.set_status(f"游戏 {app_id} 已有名称 '{current_name}'，未进行更新")
    
    def update_progress(self, message: str, progress: int):
        """更新进度信息
        
        Args:
            message: 进度消息
            progress: 进度百分比
        """
        self.view.set_status(f"{message} ({progress}%)")
    
    def handle_unlock_completed(self, success: bool, message: str, app_id: str):
        """处理解锁完成事件
        
        Args:
            success: 是否成功
            message: 消息
            app_id: 游戏AppID
        """
        # 启用按钮
        self.view.enable_buttons(True)
        
        # 显示结果消息
        self.view.set_status(message)
        
        # 如果成功，更新游戏状态
        if success:
            self.data_model.set_unlock_status(app_id, True, auto_save=True)
            
            # 刷新表格
            games = self.data_model.get_all_games()
            self.view.update_table(games)
            
            # 显示成功消息
            QMessageBox.information(
                self.view,
                "解锁成功",
                f"游戏 {app_id} 解锁成功，请重启Steam后运行游戏。"
            )
        else:
            # 显示错误消息
            QMessageBox.critical(
                self.view,
                "解锁失败",
                f"游戏 {app_id} 解锁失败:\n{message}"
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
    
    def open_steam_store(self, app_id: str):
        """打开游戏的Steam商店页面
        
        Args:
            app_id: 游戏的AppID
        """
        import webbrowser
        try:
            url = f"https://store.steampowered.com/app/{app_id}/"
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.warning(
                self.view,
                "打开失败",
                f"无法打开Steam商店页面: {str(e)}"
            )
    
    def fetch_all_game_names(self, app_ids=None, force=False):
        """批量获取游戏名称
        
        Args:
            app_ids: 要获取名称的AppID列表，如果为None则获取所有游戏
            force: 是否强制更新所有游戏名称，即使已有名称
        """
        # 获取所有游戏或选中的游戏
        if app_ids is None:
            games = self.data_model.get_all_games()
            
            # 根据force参数决定处理哪些游戏
            if not force:
                # 只处理名称为空的游戏
                empty_name_games = [game for game in games if not game.get("game_name")]
                app_ids = [game.get("app_id") for game in empty_name_games if game.get("app_id")]
            else:
                # 处理所有游戏
                app_ids = [game.get("app_id") for game in games if game.get("app_id")]
        
        if not app_ids:
            QMessageBox.information(
                self.view,
                "提示",
                "没有游戏需要获取名称"
            )
            return
        
        # 显示确认信息，根据force状态不同
        message = f"将为 {len(app_ids)} 个"
        if not force:
            message += "无名称的"
        else:
            message += "所有选中的"
        message += "游戏获取名称，这可能需要一些时间。\n\n要继续吗?"
        
        # 询问用户是否确认批量获取
        result = QMessageBox.question(
            self.view,
            "批量获取游戏名称",
            message,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 创建并显示进度对话框
        progress_dialog = QProgressDialog("正在获取游戏名称...", "取消", 0, len(app_ids), self.view)
        progress_dialog.setWindowTitle("获取进度")
        progress_dialog.setModal(True)
        progress_dialog.show()
        
        # 定义批量获取任务
        import threading
        import time
        
        def batch_fetch_task():
            # 设置最大并发数
            max_concurrent = 3
            active_threads = []
            completed = 0
            updated = 0
            canceled = False
            
            # 监控进度对话框取消按钮
            def check_canceled():
                nonlocal canceled
                if progress_dialog.wasCanceled():
                    canceled = True
                
                # 每100ms检查一次
                if not canceled:
                    QTimer.singleShot(100, check_canceled)
            
            # 开始定时检查
            QTimer.singleShot(100, check_canceled)
            
            # 计数器和锁，用于线程安全的更新进度
            import threading
            counter_lock = threading.Lock()
            
            # 定义每个游戏的获取任务
            def fetch_single_game_name(app_id, index):
                nonlocal completed, updated
                
                if canceled:
                    return
                
                try:
                    # 获取游戏当前名称
                    game = self.data_model.get_game(app_id)
                    current_name = game.get("game_name", "") if game else ""
                    
                    # 如果不强制更新且已有名称，则跳过
                    if not force and current_name:
                        return
                    
                    # 为每个游戏构建API请求
                    url = f"https://steamspy.com/api.php?request=appdetails&appid={app_id}"
                    
                    # 添加随机延迟，避免请求过快被限制
                    time.sleep(0.5 + (index % 5) * 0.2)
                    
                    # 发送请求
                    import requests
                    response = requests.get(url, timeout=5)
                    
                    # 解析响应
                    if response.status_code == 200:
                        data = response.json()
                        game_name = data.get('name')
                        
                        if game_name and len(game_name) > 1:
                            # 在主线程中更新游戏名称
                            QTimer.singleShot(0, lambda: self.update_game_name_silently(app_id, game_name, force=force))
                            
                            # 增加更新计数
                            with counter_lock:
                                updated += 1
                
                except Exception as e:
                    # 忽略单个游戏的错误，继续处理其他游戏
                    pass
                
                # 更新进度
                with counter_lock:
                    completed += 1
                    progress = int((completed / len(app_ids)) * 100)
                    QTimer.singleShot(0, lambda: progress_dialog.setValue(completed))
            
            # 批量处理所有游戏
            for i, app_id in enumerate(app_ids):
                if canceled:
                    break
                
                # 限制并发数
                while len(active_threads) >= max_concurrent:
                    # 移除已完成的线程
                    active_threads = [t for t in active_threads if t.is_alive()]
                    time.sleep(0.1)
                
                # 创建并启动新线程
                thread = threading.Thread(target=fetch_single_game_name, args=(app_id, i))
                thread.daemon = True
                thread.start()
                active_threads.append(thread)
            
            # 等待所有线程完成
            for thread in active_threads:
                thread.join()
            
            # 批量更新完成后保存数据
            self.data_model.save_data(silent=False)
            
            # 完成后关闭进度对话框并刷新表格
            QTimer.singleShot(0, progress_dialog.close)
            QTimer.singleShot(0, lambda: self.view.set_status(f"已完成 {completed}/{len(app_ids)} 个游戏处理，成功更新 {updated} 个游戏名称"))
            
            # 刷新表格
            games = self.data_model.get_all_games()
            QTimer.singleShot(0, lambda: self.view.update_table(games))
            
        # 在后台线程中执行批量获取任务
        thread = threading.Thread(target=batch_fetch_task)
        thread.daemon = True
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
                databases = game.get("databases", [])
                database_name = databases[0] if databases else ""
                self.data_model.update_game(
                    app_id,
                    database_name,
                    game_name,
                    game.get("is_unlocked", False),
                    auto_save=False  # 不立即保存，等批量操作完成后再保存
                )
        
        # 更新状态栏
        self.view.set_status(f"正在处理: {game_name}") 
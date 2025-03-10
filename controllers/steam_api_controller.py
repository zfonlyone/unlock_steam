from PyQt5.QtCore import QObject, pyqtSignal, Qt, QTimer, QPoint
from PyQt5.QtWidgets import QProgressDialog, QMessageBox, QApplication, QMenu, QAction
import threading
import time
from typing import List, Dict, Any, Optional


class SteamApiController(QObject):
    """Steam API控制器，处理游戏名称获取和其他Steam API相关操作"""
    
    # 信号定义
    fetchCompleted = pyqtSignal(str, str, str)  # app_id, game_name, error_message
    batchFetchCompleted = pyqtSignal(bool, str, int)  # success, message, updated_count
    
    def __init__(self, steam_api_model, data_model, config_model,view):
        """初始化Steam API控制器
        
        Args:
            steam_api_model: Steam API模型
            data_model: 数据管理模型
            view: 视图对象
        """
        super().__init__()
        self.steam_api_model = steam_api_model
        self.data_model = data_model
        self.config_model = config_model
        self.view = view
        
        # 取消标志
        self.cancel_batch = False
    
    def fetch_game_name(self, app_id: str, force: bool = True):
        """获取单个游戏的名称
        
        Args:
            app_id: 游戏AppID
            force: 是否强制更新，即使游戏已有名称
        """
        # 显示状态
        self.view.set_status(f"正在获取游戏 {app_id} 的名称...")

        try:
            # 获取游戏信息
            success, result = self.steam_api_model.get_game_name(app_id)

            # 处理结果
            if success:
                # 获取成功，更新数据
                game = self.data_model.get_game(app_id)
                if game:
                    databases = game.get("databases", [])
                    database_name = databases[0] if databases else "default"
                    is_unlocked = game.get("is_unlocked", False)
                else:
                    database_name = "default"
                    is_unlocked = False

                # 更新游戏数据
                self.data_model.update_game(
                    app_id=app_id,
                    database_name=database_name,
                    game_name=result,  # 游戏名称
                    auto_save=True
                )

                # 发送完成信号
                self.view.set_status(f"获取成功，更新数据...")
            else:
                # 发送完成信号
                self.view.set_status(f"获取失败，请检查网络连接...")
            
            self.view.update_table(self.data_model.get_all_games())
        except Exception as e:
            # 处理异常
            print(f"获取游戏名称异常: {e}")

            def update_ui_error():
                self.view.set_status(f"获取游戏名称时发生错误: {str(e)}")


            QTimer.singleShot(0, update_ui_error)

            # 发送完成信号
            self.fetchCompleted.emit(app_id, "", str(e))
    
    def fetch_all_game_names(self, app_ids: List[str] = None, force: bool = False):
        """批量获取游戏名称
        
        Args:
            app_ids: 游戏AppID列表，如果为None则获取所有游戏
            force: 是否强制更新，即使游戏已有名称
        """
        # 准备数据
        if app_ids is None:
            games = self.data_model.get_all_games()
            app_ids = [game.get("app_id") for game in games if game.get("app_id")]
        
        # 检查是否有游戏
        if not app_ids:
            QMessageBox.information(
                self.view,
                "提示",
                "没有需要获取名称的游戏"
            )
            return
        
        # 确认操作
        result = QMessageBox.question(
            self.view,
            "批量获取游戏名称",
            f"将为 {len(app_ids)} 个游戏获取名称，这可能需要一些时间。确定继续吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if result != QMessageBox.Yes:
            return
        
        # 重置UI状态的函数
        def reset_ui():
            # 重置UI状态
            self.view.set_status("就绪")
            
        # 显示进度信息
        self.view.set_status(f"正在获取游戏名称... (0/{len(app_ids)})")
        
        
        # 设置取消处理
        
        # 完成标志
        batch_completed = False
        
        
        # 批量获取回调函数
        def batch_callback(app_id, success, name, progress, total):
            """批量获取的回调处理"""
            # 检查是否取消


            # 更新进度信息
            progress_msg = f"正在获取游戏名称... ({progress}/{total})"
            self.view.set_status(progress_msg)
            
            # 如果成功获取，更新数据库
            if success:
                # 获取游戏数据
                game = self.data_model.get_game(app_id)
                if game:
                    databases = game.get("databases", [])
                    database_name = databases[0] if databases else "default"
                    is_unlocked = game.get("is_unlocked", False)
                else:
                    database_name = "default"
                    is_unlocked = False
                
                # 检查是否需要更新
                current_name = game.get("game_name", "") if game else ""
                if force or not current_name or current_name.startswith("Game "):
                    # 更新数据
                    self.data_model.update_game(
                        app_id=app_id,
                        database_name=database_name,
                        game_name=name,
                        auto_save=True  
                    )
                    # 每10个游戏刷新一次表格
                    if progress % 10 == 0 or progress == total:
                        all_games = self.data_model.get_all_games()
                        self.view.update_table(all_games)
                    return True  # 表示已更新
            
            return False  # 表示未更新
        
        # 批量处理线程
        def batch_worker():
            nonlocal batch_completed
            
            try:
                # 获取游戏名称
                results = self.steam_api_model.get_multiple_game_names(
                    app_ids, 
                    callback=batch_callback
                )
                
                # 保存数据
                self.data_model.save_data()
                
                # 统计更新数量
                updated_count = sum(1 for app_id in results if app_id in app_ids)
                
                # 更新UI
                def finish_batch():
                    try:

                        # 更新状态
                        self.view.set_status(f"批量获取完成: 处理了 {len(app_ids)} 个游戏，更新了 {updated_count} 个名称")
                        # 刷新表格
                        all_games = self.data_model.get_all_games()
                        self.view.update_table(all_games)
                        # 通知完成

                    except Exception as e:
                        print(f"完成UI更新失败: {e}")
                        reset_ui()
                
                
                # 发送批量完成信号
                self.batchFetchCompleted.emit(True, f"已更新 {updated_count} 个游戏名称", updated_count)
            
            except Exception as e:
                # 处理异常
                print(f"批量获取异常: {e}")
                
                # 发送批量完成信号
                self.batchFetchCompleted.emit(False, str(e), 0)
            
            finally:
                # 标记为已完成
                batch_completed = True
        
        # 启动批量处理线程
        batch_thread = threading.Thread(target=batch_worker)
        batch_thread.daemon = True
        batch_thread.start()

    
    def open_store_page(self, app_id: str):
        """打开Steam商店页面
        
        Args:
            app_id: 游戏AppID
        """
        import webbrowser
        url = f"https://store.steampowered.com/app/{app_id}/"
        webbrowser.open(url) 
    
    
    def run_game(self, app_id: str):
        """运行游戏
        
        Args:
            app_id: 游戏AppID
        """
        try:
            # 获取Steam路径
            steam_path = self.config_model.get("steam_path", "")
            if not steam_path:
                QMessageBox.warning(
                    self.view,
                    "运行游戏失败",
                    "未配置Steam路径"
                )
                return
            
            # 启动游戏
            import subprocess
            import os
            
            # 构建Steam运行命令
            run_command = f'"{os.path.join(steam_path, "steam.exe")}" -applaunch {app_id}'
            
            # 执行命令
            subprocess.Popen(run_command, shell=True)
            
            # 显示提示
            self.view.set_status(f"已启动游戏 {app_id}")
        except Exception as e:
            # 显示错误
            QMessageBox.warning(
                self.view,
                "运行游戏失败",
                f"启动游戏 {app_id} 时发生错误: {str(e)}"
            )
    
    def open_library_page(self, app_id: str):
        """跳转到Steam库中的游戏页面
        
        Args:
            app_id: 游戏AppID
        """
        import webbrowser
        url = f"steam://nav/games/details/{app_id}"
        webbrowser.open(url)
    
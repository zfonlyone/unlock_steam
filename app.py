import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, Qt

# 导入MVC组件
from models import DataManager, UnlockModel, GitModel, ConfigModel
from models.steam_api_model import SteamApiModel
from views import MainWindow, ConfigDialog
from controllers import SearchController, UnlockController, GitController, SteamApiController
from controllers.menu_manager import MenuManager

import threading
import time

class App:
    """应用程序类，负责初始化和协调MVC组件"""
    
    def __init__(self):
        # 创建配置模型
        self.config_model = ConfigModel()
        
        # 创建数据模型
        self.data_manager = DataManager()
        
        # 创建解锁模型
        self.unlock_model = UnlockModel(self.config_model.get_config())
        
        # 创建Git模型
        self.git_model = GitModel(self.config_model.get("manifest_repo_path", ""))
        
        # 创建Steam API模型
        self.steam_api_model = SteamApiModel()
        
        # 创建视图组件
        self.main_window = MainWindow()
        
        # 连接配置请求信号
        self.main_window.configRequested.connect(self.show_config_dialog)
        
        # 创建控制器组件
        self.search_controller = SearchController(self.data_manager, self.main_window)
        self.unlock_controller = UnlockController(self.data_manager, self.unlock_model, self.config_model, self.main_window)
        self.git_controller = GitController(self.data_manager, self.git_model, self.config_model, self.main_window)
        
        self.steam_api_controller = SteamApiController(
            steam_api_model=self.steam_api_model,
            data_model=self.data_manager,
            view=self.main_window
        )
        
        # 创建菜单管理器，统一管理右键菜单
        self.menu_manager = MenuManager(
            view=self.main_window,
            unlock_controller=self.unlock_controller,
            steam_api_controller=self.steam_api_controller
        )
        
        # 连接解锁控制器信号
        self.unlock_controller.unlockCompleted.connect(self.unlock_controller.handle_unlock_completed)
        
        # 连接Steam API控制器信号
        self.main_window.fetchGameNamesRequested.connect(self.steam_api_controller.fetch_all_game_names)
        
        # 启动UI守护线程
        self.start_ui_guardian()
        
        # 延迟加载数据
        QTimer.singleShot(100, self.load_initial_data)
    
    def start_ui_guardian(self):
        """启动UI守护线程，确保UI不会卡死"""
        def ui_guardian():
            last_check_time = time.time()
            check_interval = 5  # 每5秒检查一次
            
            while True:
                time.sleep(1)  # 每秒检查一次守护条件
                
                # 如果主线程已退出，守护线程也应该退出
                if not threading.main_thread().is_alive():
                    break
                
                # 定期检查UI状态
                current_time = time.time()
                if current_time - last_check_time >= check_interval:
                    last_check_time = current_time
                    
                    # 使用QTimer安全地在主线程中执行UI恢复
                    QTimer.singleShot(0, self.check_and_restore_ui)
        
        # 创建并启动UI守护线程
        guardian = threading.Thread(target=ui_guardian)
        guardian.daemon = True
        guardian.start()
        self.main_window.set_status("UI守护线程已启动")
    
    def check_and_restore_ui(self):
        """检查并恢复UI状态"""
        try:
            # 恢复按钮状态
            self.main_window.enable_buttons(True)
            # 处理挂起的事件
            QApplication.processEvents()
            self.main_window.set_status("UI守护：已检查并恢复UI状态")
        except Exception as e:
            self.main_window.set_status(f"UI守护：恢复UI状态失败: {e}")
    
    def load_initial_data(self):
        """加载初始数据"""
        # 检查配置是否有效
        if not self.config_model.is_valid_config():
            # 显示配置错误提示
            QMessageBox.warning(
                self.main_window,
                "配置错误",
                "配置无效，请先配置Steam路径和清单仓库路径。"
            )
            # 显示配置对话框
            self.show_config_dialog()
            return
        
        # 初始化数据
        games = self.data_manager.get_all_games()
        
        # 更新表格，即使没有游戏数据
        self.main_window.update_table(games)
        
        # 设置状态
        if games:
            self.main_window.set_status(f"已加载 {len(games)} 个游戏")
        else:
            # 如果没有游戏数据，显示提示信息
            self.main_window.set_status("没有游戏数据，请点击'更新列表'按钮从仓库获取数据")
            QMessageBox.information(
                self.main_window,
                "提示",
                "没有游戏数据，请点击'更新列表'按钮从仓库获取数据，然后点击'刷新显示'按钮查看更新后的数据。"
            )
    
    def show_config_dialog(self):
        """显示配置对话框"""
        dialog = ConfigDialog(self.main_window, self.config_model.get_config())
        dialog.configSaved.connect(self.on_config_saved)
        dialog.exec_()
    
    def on_config_saved(self, config):
        """处理配置保存事件
        
        Args:
            config: 新的配置字典
        """
        # 更新配置
        for key, value in config.items():
            self.config_model.set(key, value)
        
        # 保存配置
        if self.config_model.save_config():
            # 重新初始化依赖配置的模型组件
            self.unlock_model = UnlockModel(self.config_model.get_config())
            self.git_model = GitModel(self.config_model.get("manifest_repo_path", ""))
            
            # 更新控制器引用的模型
            # 注意：GitController保存的仍然是原始配置模型的引用，但内容已更新
            self.git_controller.git_model = self.git_model
            
            # 显示成功提示
            QMessageBox.information(
                self.main_window,
                "配置保存成功",
                "配置已保存。您现在可以点击'更新列表'按钮获取游戏数据。"
            )
            
            # 重新加载数据
            self.load_initial_data()
        else:
            QMessageBox.critical(
                self.main_window,
                "保存失败",
                "配置保存失败，请检查文件权限。"
            )
    
    def run(self):
        """运行应用程序"""
        self.main_window.show()

def main():
    """应用程序入口函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 设置应用程序风格
    
    # 显示启动画面
    splash_pixmap = QPixmap("screenshot.png")
    splash = QSplashScreen(splash_pixmap, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()
    
    # 创建并运行应用程序
    steam_app = App()
    
    # 关闭启动画面，显示主窗口
    splash.finish(steam_app.main_window)
    
    # 运行应用
    steam_app.run()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
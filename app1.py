import sys
import os
import json
from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import QTimer

# 导入MVC组件
from models import DataManager, UnlockModel, GitModel, ConfigModel
from views import MainWindow, ConfigDialog
from controllers import SearchController, UnlockController, GitController

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
        
        # 创建视图组件
        self.main_window = MainWindow()
        
        # 连接配置请求信号
        self.main_window.configRequested.connect(self.show_config_dialog)
        
        # 创建控制器组件
        self.search_controller = SearchController(
            model=self.data_manager,
            view=self.main_window
        )
        
        self.unlock_controller = UnlockController(
            data_model=self.data_manager,
            unlock_model=self.unlock_model,
            config_model=self.config_model,
            view=self.main_window
        )
        
        self.git_controller = GitController(
            data_model=self.data_manager,
            git_model=self.git_model,
            config_model=self.config_model,
            view=self.main_window
        )
        
        # 延迟加载数据
        QTimer.singleShot(100, self.load_initial_data)
    
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
        
        # 如果本地数据文件存在，加载数据
        if os.path.exists(self.data_manager.data_file):
            games = self.data_manager.get_all_games()
            self.main_window.update_table(games)
            self.main_window.set_status(f"已加载 {len(games)} 个游戏")
        else:
            QMessageBox.information(
                self.main_window,
                "提示",
                "未找到本地数据文件，请点击'更新列表'按钮从仓库获取数据。"
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
            # 重新初始化依赖配置的组件
            self.unlock_model = UnlockModel(self.config_model.get_config())
            self.git_model = GitModel(self.config_model.get("manifest_repo_path", ""))
            
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
    
    # 创建并运行应用程序
    steam_app = App()
    steam_app.run()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
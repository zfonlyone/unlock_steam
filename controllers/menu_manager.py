from PyQt5.QtWidgets import QMenu, QAction, QApplication
from PyQt5.QtCore import QObject, QPoint
from PyQt5.QtGui import QClipboard


class MenuManager(QObject):
    """菜单管理器，协调多个控制器的右键菜单"""
    
    def __init__(self, view, unlock_controller, steam_api_controller):
        """初始化菜单管理器
        
        Args:
            view: 视图对象
            unlock_controller: 解锁控制器
            steam_api_controller: Steam API控制器
        """
        super().__init__()
        self.view = view
        self.unlock_controller = unlock_controller
        self.steam_api_controller = steam_api_controller
        
        # 连接视图信号到菜单管理器
        self.view.contextMenuRequested.connect(self.show_context_menu)
    
    def show_context_menu(self, position: QPoint, game_data: dict):
        """显示右键菜单
        
        Args:
            position: 菜单位置
            game_data: 游戏数据
        """
        if not game_data:
            return
        
        # 获取游戏信息
        app_id = game_data.get("app_id", "")
        game_name = game_data.get("game_name", "")
        is_unlocked = game_data.get("is_unlocked", False)
        
        # 创建菜单
        context_menu = QMenu(self.view)
        
        # 解锁相关菜单项
        if is_unlocked:
            remove_action = QAction("取消解锁", self.view)
            remove_action.triggered.connect(lambda: self.unlock_controller.remove_unlock(app_id))
            context_menu.addAction(remove_action)
        else:
            unlock_action = QAction("解锁游戏", self.view)
            unlock_action.triggered.connect(lambda: self.unlock_controller.unlock_game(app_id))
            context_menu.addAction(unlock_action)
        
        
        # 添加分隔线
        context_menu.addSeparator()
        
        # Steam API相关菜单项
        get_name_action = QAction("获取游戏名称", self.view)
        get_name_action.triggered.connect(lambda: self.steam_api_controller.fetch_game_name(app_id))
        context_menu.addAction(get_name_action)
        
        open_store_action = QAction("打开Steam商店页面", self.view)
        open_store_action.triggered.connect(lambda: self.steam_api_controller.open_store_page(app_id))
        context_menu.addAction(open_store_action)
        
        # 添加运行游戏菜单项
        run_game_action = QAction("运行游戏", self.view)
        run_game_action.triggered.connect(lambda: self.steam_api_controller.run_game(app_id))
        context_menu.addAction(run_game_action)
        
        # 添加分隔线
        context_menu.addSeparator()
        
        # 通用菜单项
        copy_action = QAction(f"复制AppID: {app_id}", self.view)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(app_id))
        context_menu.addAction(copy_action)
        
        copy_game_name= QAction(f"复制name: {game_name}", self.view)
        copy_game_name.triggered.connect(lambda: QApplication.clipboard().setText(game_name))
        context_menu.addAction(copy_game_name)
        
        # 显示菜单
        context_menu.exec_(position) 
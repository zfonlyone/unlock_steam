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
        if is_unlocked == "disabled":
            enable_action = QAction("重新启用", self.view)
            enable_action.triggered.connect(lambda: self.view.toggleUnlockRequested.emit(game_data))
            context_menu.addAction(enable_action)
            
            remove_action = QAction("取消解锁 (彻底删除)", self.view)
            remove_action.triggered.connect(lambda: self.unlock_controller.remove_unlock(app_id))
            context_menu.addAction(remove_action)
        elif is_unlocked:
            disable_action = QAction("禁用解锁", self.view)
            disable_action.triggered.connect(lambda: self.view.toggleUnlockRequested.emit(game_data))
            context_menu.addAction(disable_action)
            
            remove_action = QAction("取消解锁", self.view)
            remove_action.triggered.connect(lambda: self.unlock_controller.remove_unlock(app_id))
            context_menu.addAction(remove_action)
        else:
            unlock_action = QAction("解锁游戏", self.view)
            unlock_action.triggered.connect(lambda: self.unlock_controller.unlock_game(app_id))
            context_menu.addAction(unlock_action)
        
        # 清单管理选项
        if is_unlocked:
            context_menu.addSeparator()
            
            # 更新 Lua 文件（从远程重新下载）
            update_lua_action = QAction("更新Lua文件", self.view)
            update_lua_action.triggered.connect(lambda: self.unlock_controller.update_lua_from_remote(app_id))
            context_menu.addAction(update_lua_action)
            
            # 单个游戏的固定清单管理
            disable_man_single_action = QAction("禁用固定清单", self.view)
            disable_man_single_action.triggered.connect(lambda: self.unlock_controller.toggle_single_manifest(app_id, False))
            context_menu.addAction(disable_man_single_action)
            
            enable_man_single_action = QAction("启用固定清单", self.view)
            enable_man_single_action.triggered.connect(lambda: self.unlock_controller.toggle_single_manifest(app_id, True))
            context_menu.addAction(enable_man_single_action)

            # 更新清单 (API) - 仅限未禁用的
            if is_unlocked != "disabled":
                update_man_action = QAction("更新清单 (API)", self.view)
                update_man_action.triggered.connect(lambda: self.view.updateManifestRequested.emit(game_data))
                context_menu.addAction(update_man_action)
            
            # 获取并添加 DLC
            fetch_dlc_action = QAction("获取并添加 DLC", self.view)
            fetch_dlc_action.triggered.connect(lambda: self.unlock_controller.fetch_and_add_dlc(app_id))
            context_menu.addAction(fetch_dlc_action)
            
            # 补全清单
            complete_manifest_action = QAction("补全清单", self.view)
            complete_manifest_action.triggered.connect(lambda: self.unlock_controller.complete_manifests(app_id))
            context_menu.addAction(complete_manifest_action)
        
        
        # 添加分隔线
        context_menu.addSeparator()
        
        # Steam API相关菜单项
        get_name_action = QAction("获取游戏名称", self.view)
        get_name_action.triggered.connect(lambda: self.steam_api_controller.fetch_game_name(app_id))
        context_menu.addAction(get_name_action)
        
        open_store_action = QAction("打开Steam商店页面", self.view)
        open_store_action.triggered.connect(lambda: self.steam_api_controller.open_store_page(app_id))
        context_menu.addAction(open_store_action)
        
        # 跳转至库
        open_library_action = QAction("跳转至库", self.view)
        open_library_action.triggered.connect(lambda: self.steam_api_controller.open_library_page(app_id))
        context_menu.addAction(open_library_action)
        
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
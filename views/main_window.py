from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QStatusBar, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint
from PyQt5.QtGui import QColor

class MainWindow(QMainWindow):
    """主应用程序窗口(View层)"""
    
    # 定义信号，用于和Controller层通信
    searchRequested = pyqtSignal(str)  # 搜索请求
    refreshDisplayRequested = pyqtSignal()  # 刷新显示请求
    checkUnlockStatusRequested = pyqtSignal(bool)  # 检查解锁状态请求
    fetchGameNamesRequested = pyqtSignal()  # 获取游戏名称请求
    updateListRequested = pyqtSignal()  # 更新列表请求
    contextMenuRequested = pyqtSignal(QPoint, object)  # 右键菜单请求
    configRequested = pyqtSignal()  # 配置请求
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("Steam解锁文件管理器")
        self.resize(800, 600)
        
        # 设置应用程序图标和主题色调
        self.setStyleSheet("QMainWindow { background-color: #f5f5f5; }")
        
        # 添加菜单栏
        self.setup_menu()
        
        # 创建主部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 添加搜索和按钮区域
        top_layout = QHBoxLayout()
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入AppID、游戏名称或@Steam链接 (例如: @https://store.steampowered.com/app/123456/)")
        self.search_input.returnPressed.connect(self._on_search)
        
        # 功能按钮
        refresh_btn = QPushButton("刷新显示")
        refresh_btn.clicked.connect(self._on_refresh_display)
        
        check_unlock_btn = QPushButton("检查解锁状态")
        check_unlock_btn.clicked.connect(self._on_check_unlock_status)
        
        get_names_btn = QPushButton("获取游戏名称")
        get_names_btn.clicked.connect(self._on_fetch_game_names)
        
        update_list_btn = QPushButton("更新列表")
        update_list_btn.clicked.connect(self._on_update_list)
        
        # 将组件添加到顶部布局
        top_layout.addWidget(self.search_input)
        top_layout.addWidget(refresh_btn)
        top_layout.addWidget(check_unlock_btn)
        top_layout.addWidget(get_names_btn)
        top_layout.addWidget(update_list_btn)
        
        # 将顶部布局添加到主布局
        main_layout.addLayout(top_layout)
        
        # 创建游戏列表表格
        self.game_table = QTableWidget(0, 2)  # 初始化为0行2列
        self.game_table.setHorizontalHeaderLabels(["AppID", "游戏名称"])
        self.game_table.setAlternatingRowColors(True)
        self.game_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.game_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.game_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.game_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self._on_context_menu)
        
        # 将表格添加到主布局
        main_layout.addWidget(self.game_table)
        
        # 添加状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.set_status("就绪")
        
        # 禁用一些功能按钮，直到数据加载
        self.enable_buttons(False)
    
    def setup_menu(self):
        """设置菜单栏"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        
        # 配置选项
        config_action = QAction("设置", self)
        config_action.triggered.connect(self._on_config)
        file_menu.addAction(config_action)
        
        # 分隔符
        file_menu.addSeparator()
        
        # 退出选项
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")
        
        # 关于选项
        about_action = QAction("关于", self)
        about_action.triggered.connect(self._on_about)
        help_menu.addAction(about_action)
    
    def _on_search(self):
        """处理搜索请求"""
        query = self.search_input.text().strip()
        if not query:
            return
            
        # 检查是否是Steam链接
        if self._is_steam_link(query):
            try:
                # 提取AppID
                app_id = self._extract_appid_from_link(query)
                if app_id:
                    self.set_status(f"从链接中提取AppID: {app_id}")
                    
                    # 将AppID作为新的查询内容
                    query = app_id
                    
                    # 更新搜索框
                    self.search_input.setText(app_id)
            except Exception as e:
                self.set_status(f"从链接中提取AppID失败: {str(e)}")
        
        # 发送搜索请求
        self.searchRequested.emit(query)
    
    def _is_steam_link(self, text):
        """检查文本是否是Steam链接
        
        Args:
            text: 要检查的文本
            
        Returns:
            是否是Steam链接
        """
        # 支持以@开头的标记格式
        if text.startswith('@') and ('store.steampowered.com' in text or 'steamcommunity.com' in text):
            return True
        
        # 支持直接粘贴的完整链接
        if text.startswith(('http://', 'https://')) and ('store.steampowered.com' in text or 'steamcommunity.com' in text):
            return True
            
        return False
    
    def _extract_appid_from_link(self, text):
        """从Steam链接中提取AppID
        
        Args:
            text: 包含Steam链接的文本
            
        Returns:
            提取到的AppID，如果提取失败则返回None
        """
        import re
        
        # 移除@前缀（如果有）
        if text.startswith('@'):
            text = text[1:]
        
        # 尝试匹配不同格式的Steam链接
        patterns = [
            r'store\.steampowered\.com/app/(\d+)',  # 商店页面链接
            r'steamcommunity\.com/app/(\d+)',       # 社区页面链接
            r'steamcommunity\.com/games/(\d+)',     # 游戏社区链接
            r'/app/(\d+)',                          # 简短格式
            r'appid=(\d+)',                         # 查询参数格式
            r'app_id=(\d+)',                        # 另一种查询参数格式
            r'[/=](\d{5,10})[/]?'                   # 通用数字格式（假设AppID是5-10位数字）
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        
        return None
    
    def _on_refresh_display(self):
        """处理刷新显示请求"""
        self.refreshDisplayRequested.emit()
    
    def _on_check_unlock_status(self):
        """处理检查解锁状态请求"""
        self.checkUnlockStatusRequested.emit(True)
    
    def _on_fetch_game_names(self):
        """处理获取游戏名称请求"""
        self.fetchGameNamesRequested.emit()
    
    def _on_update_list(self):
        """处理更新列表请求"""
        self.updateListRequested.emit()
    
    def _on_context_menu(self, position: QPoint):
        """处理右键菜单请求"""
        row = self.game_table.rowAt(position.y())
        if row >= 0:
            # 获取选中行的数据
            appid = self.game_table.item(row, 0).text()
            name = self.game_table.item(row, 1).text()
            selected_game = {"app_id": appid, "game_name": name}
            
            # 在所选行上发射上下文菜单信号
            self.contextMenuRequested.emit(self.game_table.viewport().mapToGlobal(position), selected_game)
    
    def _on_config(self):
        """处理配置请求"""
        self.configRequested.emit()
    
    def _on_about(self):
        """处理关于请求"""
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.about(
            self, 
            "关于Steam游戏解锁器",
            "Steam游戏解锁器 v1.0\n\n"
            "本工具用于管理和解锁Steam游戏。\n"
            "可以帮助您轻松查找、解锁Steam游戏。\n\n"
            "请遵守当地法律法规使用此工具。"
        )
    
    def update_table(self, games):
        """更新游戏表格"""
        self.game_table.setRowCount(0)  # 清空表格
        
        # 即使没有游戏数据，也启用功能按钮（尤其是更新列表按钮）
        self.enable_buttons(True)
        
        # 如果没有游戏数据，直接返回，保持表格为空
        if not games:
            return
        
        # 填充表格
        for i, game in enumerate(games):
            self.game_table.insertRow(i)
            
            # 添加AppID列
            appid_item = QTableWidgetItem(str(game.get("app_id", "")))
            self.game_table.setItem(i, 0, appid_item)
            
            # 添加游戏名称列
            name_item = QTableWidgetItem(game.get("game_name", ""))
            self.game_table.setItem(i, 1, name_item)
            
            # 如果游戏已解锁，设置行背景色为浅绿色
            if game.get("is_unlocked", False):
                for col in range(2):
                    item = self.game_table.item(i, col)
                    if item:
                        item.setBackground(QColor(200, 255, 200))  # 浅绿色
        
        # 更新状态栏
        self.set_status(f"显示 {len(games)} 个游戏")
    
    def set_status(self, message):
        """设置状态栏消息"""
        self.status_bar.showMessage(message)
    
    def enable_buttons(self, enabled=True):
        """启用或禁用功能按钮"""
        for i in range(1, 5):  # 除了搜索框外的按钮
            widget = self.centralWidget().layout().itemAt(0).layout().itemAt(i).widget()
            if widget:
                widget.setEnabled(enabled) 
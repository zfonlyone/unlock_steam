import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTableView, QHeaderView,
    QLineEdit, QStatusBar, QMenu, QAction
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, pyqtSlot, QAbstractTableModel, QVariant, QModelIndex
from PyQt5.QtGui import QColor, QIcon

class GameTableModel(QAbstractTableModel):
    """自定义数据模型，用于高效显示和排序"""
    def __init__(self, games=None, theme="dark"):
        super().__init__()
        self._games = games or []
        self._headers = ["AppID", "游戏名称"]
        self._theme = theme

    def set_theme(self, theme):
        self._theme = theme
        self.layoutChanged.emit()

    def rowCount(self, parent=QModelIndex()):
        return len(self._games)

    def columnCount(self, parent=QModelIndex()):
        return 2

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._games)):
            return QVariant()

        game = self._games[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == 0: return str(game.get("app_id", ""))
            if col == 1: return game.get("game_name", "")

        if role == Qt.BackgroundRole:
            status = game.get("is_unlocked")
            if status == "disabled":
                return QColor(100, 30, 30) if self._theme == "dark" else QColor(255, 100, 100)
            if status:
                return QColor(64, 98, 70) if self._theme == "dark" else QColor(200, 255, 200)

        if role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter | Qt.AlignLeft

        return QVariant()

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self._headers[section]
        return QVariant()

    def update_data(self, games):
        self.beginResetModel()
        self._games = list(games)
        self.endResetModel()

    def get_game(self, row):
        if 0 <= row < len(self._games):
            return self._games[row]
        return None

    def sort(self, column, order):
        """极其高效的数值排序"""
        self.layoutAboutToBeChanged.emit()
        reverse = (order == Qt.DescendingOrder)
        
        def sort_key(game):
            val = game.get("app_id" if column == 0 else "game_name", "")
            if column == 0:
                try: return int(val)
                except: return 0
            return str(val).lower()

        self._games.sort(key=sort_key, reverse=reverse)
        self.layoutChanged.emit()

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
    aboutRequested = pyqtSignal()  # 关于请求
    batchUnlockRequested = pyqtSignal()  # 一键解锁请求
    themeChanged = pyqtSignal(str)  # 主题切换信号 (dark/light)
    syncRequested = pyqtSignal(list) # 增量同步请求
    
    # 工具相关信号
    toolCheckAddAppIDRequested = pyqtSignal()
    toolReplaceManifestRequested = pyqtSignal()
    toolEnableManifestRequested = pyqtSignal()
    toolFindNoManifestRequested = pyqtSignal()
    toolCleanInvalidLuaRequested = pyqtSignal()  # 清理无效 Lua 文件
    toolFixFormatsRequested = pyqtSignal()
    fetchAllDlcRequested = pyqtSignal()  # 一键获取所有 DLC
    
    # 更多右键菜单动作
    updateManifestRequested = pyqtSignal(object)  # 更新清单请求
    toggleUnlockRequested = pyqtSignal(object)    # 禁用/启用切换请求

    DARK_STYLE = """
        QMainWindow, QWidget#centralWidget { background-color: #1e1e2e; color: #cdd6f4; }
        QWidget { background-color: #1e1e2e; color: #cdd6f4; font-size: 14px; }
        QDialog, QFrame, QGroupBox { background-color: #1e1e2e; color: #cdd6f4; }
        QLineEdit { 
            background-color: #313244; border: 1px solid #45475a; 
            border-radius: 8px; padding: 10px 15px; color: #cdd6f4; 
            font-size: 15px;
        }
        QPushButton { 
            background-color: #45475a; color: #cdd6f4; border-radius: 8px; 
            padding: 10px 18px; font-weight: bold; min-width: 90px;
            font-size: 14px;
        }
        QPushButton:hover { background-color: #585b70; border: 1px solid #89b4fa; }
        QPushButton#tool_btn { 
            background-color: #313244; color: #cdd6f4; border: 1px solid #45475a;
            font-size: 13px; padding: 7px 12px; font-weight: normal; min-width: 70px;
        }
        QPushButton#tool_btn:hover { background-color: #45475a; border-color: #89b4fa; }
        
        QPushButton#batch_unlock_btn { background-color: #89b4fa; color: #11111b; }
        QPushButton#update_list_btn { background-color: #94e2d5; color: #11111b; }
        QPushButton#theme_toggle_btn { background-color: #f5e0dc; color: #11111b; min-width: 40px; }
        QTableView { background-color: #181825; alternate-background-color: #1e1e2e; color: #cdd6f4; border: 1px solid #313244; gridline-color: #313244; }
        QHeaderView::section { background-color: #11111b; color: #bac2de; padding: 8px; border: none; font-weight: bold; }
        QStatusBar { background-color: #11111b; color: #a6adc8; }
    """

    LIGHT_STYLE = """
        QMainWindow, QWidget#centralWidget { background-color: #f8f9fa; color: #212529; }
        QWidget { background-color: #f8f9fa; color: #212529; font-size: 14px; }
        QDialog, QFrame, QGroupBox { background-color: #ffffff; color: #212529; }
        QLineEdit { 
            background-color: #ffffff; border: 1px solid #ced4da; 
            border-radius: 8px; padding: 10px 15px; color: #212529; 
            font-size: 15px;
        }
        QPushButton { 
            background-color: #e9ecef; color: #212529; border-radius: 8px; 
            padding: 10px 18px; font-weight: bold; min-width: 90px;
            border: 1px solid #dee2e6; font-size: 14px;
        }
        QPushButton:hover { background-color: #dee2e6; border: 1px solid #adb5bd; }
        QPushButton#tool_btn { 
            background-color: #f8f9fa; color: #495057; border: 1px solid #ced4da;
            font-size: 13px; padding: 7px 12px; font-weight: normal; min-width: 70px;
        }
        QPushButton#tool_btn:hover { background-color: #e9ecef; border-color: #0d6efd; }
        
        QPushButton#batch_unlock_btn { background-color: #0d6efd; color: #ffffff; }
        QPushButton#update_list_btn { background-color: #198754; color: #ffffff; }
        QPushButton#theme_toggle_btn { background-color: #ffc107; color: #212529; min-width: 40px; }
        QTableView { background-color: #ffffff; alternate-background-color: #f8f9fa; color: #212529; border: 1px solid #dee2da; gridline-color: #dee2da; }
        QHeaderView::section { background-color: #e9ecef; color: #495057; padding: 8px; border: none; font-weight: bold; }
        QStatusBar { background-color: #f8f9fa; color: #6c757d; }
    """
    
    def __init__(self):
        super().__init__()
        self.current_theme = "dark"
        self.appid_to_row = {}
        self.game_data = [] # 内存中的原始数据列表
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("Steam 游戏解锁管理工具 v2.3.0")
        self.resize(1000, 700)
        
        # 设置应用程序图标 - 指向项目根目录中的 app_icon.png
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 添加菜单栏
        self.setup_menu()
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)
        
        # 顶部布局
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        refresh_btn = QPushButton("刷新显示")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._on_refresh_display)
        
        check_unlock_btn = QPushButton("检查解锁状态")
        check_unlock_btn.setCursor(Qt.PointingHandCursor)
        check_unlock_btn.clicked.connect(self._on_check_unlock_status)
        
        get_names_btn = QPushButton("获取名称")
        get_names_btn.setCursor(Qt.PointingHandCursor)
        get_names_btn.clicked.connect(self._on_fetch_game_names)
        
        update_list_btn = QPushButton("拉取清单库")
        update_list_btn.setObjectName("update_list_btn")
        update_list_btn.setCursor(Qt.PointingHandCursor)
        update_list_btn.clicked.connect(self._on_update_list)
        
        batch_unlock_btn = QPushButton("一键解锁")
        batch_unlock_btn.setObjectName("batch_unlock_btn")
        batch_unlock_btn.setCursor(Qt.PointingHandCursor)
        batch_unlock_btn.clicked.connect(self._on_batch_unlock)
        batch_unlock_btn.setToolTip("扫描并解锁所有未解锁的游戏")
        
        self.theme_btn = QPushButton("🌙")
        self.theme_btn.setObjectName("theme_toggle_btn")
        self.theme_btn.setToolTip("切换明亮/暗色模式")
        self.theme_btn.clicked.connect(self._toggle_theme)
        top_layout.addWidget(self.theme_btn)

        # 核心操作按钮
        top_layout.addWidget(refresh_btn)
        top_layout.addWidget(check_unlock_btn)
        top_layout.addWidget(update_list_btn)
        top_layout.addWidget(batch_unlock_btn)
        
        main_layout.addLayout(top_layout)
        
        # 工具栏第二行：高级管理与名称获取
        tools_layout = QHBoxLayout()
        tools_layout.setSpacing(10)
        
        get_names_btn = QPushButton("🏷️ 获取名称")
        get_names_btn.setToolTip("从 API 补充缺失的名称")
        get_names_btn.clicked.connect(self._on_fetch_game_names)
        
        check_appid_btn = QPushButton("🔍 校验lua")
        check_appid_btn.setToolTip("检查 Lua 参数非法字符")
        check_appid_btn.clicked.connect(self.toolCheckAddAppIDRequested.emit)
        
        disable_man_btn = QPushButton("🔒 禁用固定清单")
        disable_man_btn.setToolTip("批量注释 setManifestid 以禁用固定清单")
        disable_man_btn.clicked.connect(self.toolReplaceManifestRequested.emit)
        
        enable_man_btn = QPushButton("🔓 启用固定清单")
        enable_man_btn.setToolTip("批量取消 setManifestid 的注释")
        enable_man_btn.clicked.connect(self.toolEnableManifestRequested.emit)
        
        find_no_man_btn = QPushButton("👻 寻找无清单")
        find_no_man_btn.setToolTip("扫描不含清单的 Lua 文件")
        find_no_man_btn.clicked.connect(self.toolFindNoManifestRequested.emit)
        
        clean_lua_btn = QPushButton("🧹 清理无效Lua")
        clean_lua_btn.setToolTip("删除只有基础 addappid 的无效 Lua 文件")
        clean_lua_btn.clicked.connect(self.toolCleanInvalidLuaRequested.emit)
        
        fix_formats_btn = QPushButton("🪄 修复格式")
        fix_formats_btn.setToolTip("优化 Lua 格式 (移除 None，修正标帜)")
        fix_formats_btn.clicked.connect(self.toolFixFormatsRequested.emit)
        
        fetch_dlc_btn = QPushButton("📦 获取DLC")
        fetch_dlc_btn.setToolTip("一键为所有游戏获取并添加 DLC")
        fetch_dlc_btn.clicked.connect(self.fetchAllDlcRequested.emit)
        
        for btn in [get_names_btn, check_appid_btn, disable_man_btn, enable_man_btn, find_no_man_btn, clean_lua_btn, fix_formats_btn, fetch_dlc_btn]:

            btn.setObjectName("tool_btn")
            btn.setCursor(Qt.PointingHandCursor)
            tools_layout.addWidget(btn)
        
        tools_layout.addStretch(1) # 右侧留白
        main_layout.addLayout(tools_layout)
        
        # 第三行：搜索框
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 输入 AppID、游戏名称或 Steam 链接...")
        self.search_input.returnPressed.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        main_layout.addLayout(search_layout)
        
        # 使用 QTableView 替代 QTableWidget
        self.game_table = QTableView()
        self.game_model = GameTableModel(theme=self.current_theme)
        self.game_table.setModel(self.game_model)
        
        self.game_table.setAlternatingRowColors(True)
        self.game_table.setSelectionBehavior(QTableView.SelectRows)
        self.game_table.setSelectionMode(QTableView.ExtendedSelection)
        self.game_table.setShowGrid(True)
        self.game_table.setSortingEnabled(True)
        
        # 优化头部
        header = self.game_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        
        self.game_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.game_table.customContextMenuRequested.connect(self._on_context_menu)
        
        main_layout.addWidget(self.game_table)
        
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.set_status("就绪")
        
        self.enable_buttons(True)
    
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
    
    def _on_batch_unlock(self):
        """处理一键解锁请求"""
        self.batchUnlockRequested.emit()
    
    def _on_context_menu(self, position: QPoint):
        """处理右键菜单请求"""
        index = self.game_table.indexAt(position)
        if index.isValid():
            game = self.game_model.get_game(index.row())
            if game:
                self.contextMenuRequested.emit(self.game_table.viewport().mapToGlobal(position), game)
    
    def _on_config(self):
        """处理配置请求"""
        self.configRequested.emit()
    
    def _on_about(self):
        """处理关于请求"""
        # 发出关于请求信号，让Controller处理
        self.aboutRequested.emit()
    
    @pyqtSlot(list)
    def update_table(self, games):
        """核心优化：一键刷新 Model，由 Qt 处理虚拟渲染"""
        self.game_data = list(games)
        self.appid_to_row = {str(g.get("app_id")): i for i, g in enumerate(self.game_data)}
        self.game_model.update_data(self.game_data)
        self.set_status(f"显示 {len(games)} 个游戏")

    @pyqtSlot(list)
    def sync_games_to_table(self, games):
        """增量同步优化"""
        if not games: return
        changed = False
        for g in games:
            aid = str(g.get("app_id"))
            if aid in self.appid_to_row:
                idx = self.appid_to_row[aid]
                self.game_data[idx].update(g)
                changed = True
            else:
                self.appid_to_row[aid] = len(self.game_data)
                self.game_data.append(g)
                changed = True
        
        if changed:
            self.game_model.update_data(self.game_data)
        self.set_status(f"已同步 {len(self.game_data)} 个游戏...")

    @pyqtSlot(bool)
    def enable_buttons(self, enabled=True):
        """启用或禁用功能按钮（通过 top_layout 获取）"""
        # 注意：这里我们只处理顶层布局中的按钮
        children = self.centralWidget().findChildren(QPushButton)
        for btn in children:
            btn.setEnabled(enabled)

    def _toggle_theme(self):
        """切换主题"""
        new_theme = "light" if self.current_theme == "dark" else "dark"
        self.set_theme(new_theme)
        self.themeChanged.emit(new_theme)

    @pyqtSlot(str)
    def set_theme(self, theme_name):
        """设置主题样式"""
        self.current_theme = theme_name
        if theme_name == "dark":
            self.setStyleSheet(self.DARK_STYLE)
            self.theme_btn.setText("🌙")
        else:
            self.setStyleSheet(self.LIGHT_STYLE)
            self.theme_btn.setText("☀️")
        self.game_model.set_theme(theme_name)
    
    @pyqtSlot(str)
    def set_status(self, message):
        """设置状态栏消息"""
        self.status_bar.showMessage(message)
    
    @pyqtSlot(bool)
    def enable_buttons(self, enabled=True):
        """启用或禁用功能按钮"""
        for i in range(1, 5):  # 除了搜索框外的按钮
            widget = self.centralWidget().layout().itemAt(0).layout().itemAt(i).widget()
            if widget:
                widget.setEnabled(enabled) 
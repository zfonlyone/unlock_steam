import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox, QGroupBox, QTabWidget,
    QWidget, QListWidget, QListWidgetItem, QCheckBox, QComboBox,
    QFormLayout, QSpacerItem, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon


# 默认路径
DEFAULT_STEAM_PATH = "C:/Program Files (x86)/Steam"
GITHUB_REPO_URL = "https://github.com/SteamAutoCracks/ManifestHub"


class ConfigDialog(QDialog):
    """配置对话框 - 支持多仓库和 API 密钥设置"""
    
    configSaved = pyqtSignal(dict)
    _validationResult = pyqtSignal(bool, str)  # 内部信号：验证结果
    
    DARK_STYLE = """
        QDialog { background-color: #1e1e2e; color: #cdd6f4; }
        QTabWidget::pane { border: 1px solid #313244; background-color: #1e1e2e; border-radius: 6px; }
        QTabBar::tab { background-color: #11111b; color: #a6adc8; padding: 10px 20px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
        QTabBar::tab:selected { background-color: #1e1e2e; color: #89b4fa; border-bottom: 2px solid #89b4fa; }
        QGroupBox { font-weight: bold; border: 1px solid #313244; border-radius: 8px; margin-top: 15px; padding-top: 15px; background-color: #181825; }
        QGroupBox::title { left: 10px; color: #89b4fa; }
        QLineEdit, QComboBox { background-color: #313244; border: 1px solid #45475a; border-radius: 6px; padding: 8px; color: #cdd6f4; }
        QPushButton { background-color: #45475a; color: #cdd6f4; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
        QPushButton:hover { background-color: #585b70; }
        QPushButton#save_btn { background-color: #89b4fa; color: #11111b; }
        QListWidget { background-color: #11111b; border: 1px solid #313244; color: #cdd6f4; }
        QCheckBox, QLabel { color: #cdd6f4; }
        QWidget#basic_tab, QWidget#repo_tab, QWidget#api_tab { background-color: #1e1e2e; }
    """

    LIGHT_STYLE = """
        QDialog { background-color: #f8f9fa; color: #212529; }
        QTabWidget::pane { border: 1px solid #dee2e6; background-color: #ffffff; border-radius: 6px; }
        QTabBar::tab { background-color: #e9ecef; color: #495057; padding: 10px 20px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
        QTabBar::tab:selected { background-color: #ffffff; color: #0d6efd; border-bottom: 2px solid #0d6efd; }
        QGroupBox { font-weight: bold; border: 1px solid #dee2e6; border-radius: 8px; margin-top: 15px; padding-top: 15px; background-color: #f8f9fa; }
        QGroupBox::title { left: 10px; color: #0d6efd; }
        QLineEdit, QComboBox { background-color: #ffffff; border: 1px solid #ced4da; border-radius: 6px; padding: 8px; color: #212529; }
        QPushButton { background-color: #e9ecef; color: #212529; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
        QPushButton:hover { background-color: #dee2e6; }
        QPushButton#save_btn { background-color: #0d6efd; color: #ffffff; }
        QListWidget { background-color: #ffffff; border: 1px solid #dee2e6; color: #212529; }
        QCheckBox, QLabel { color: #212529; }
        QWidget#basic_tab, QWidget#repo_tab, QWidget#api_tab { background-color: #ffffff; }
    """
    
    def __init__(self, parent=None, config=None):
        super().__init__(parent)
        self.config = config or {
            "steam_path": "", 
            "manifest_repo_path": "", 
            "preferred_unlock_tool": "steamtools",
            "lua_path": "",
            "api_key": "",
            "repositories": [],
            "view_mode": "grid"
        }
        self.setup_ui()
        self.auto_fill_defaults()
        self.load_repositories()
        
    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("Steam游戏解锁器 - 配置")
        self.setMinimumWidth(650)
        self.setMinimumHeight(550)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # 设置应用程序图标
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 设置初始主题
        self.set_theme(self.config.get("theme", "dark"))
        
        layout = QVBoxLayout()
        
        # 创建选项卡
        tabs = QTabWidget()
        
        basic_tab = self.create_basic_tab()
        basic_tab.setObjectName("basic_tab")
        
        repo_tab = self.create_repo_tab()
        repo_tab.setObjectName("repo_tab")
        
        api_tab = self.create_api_tab()
        api_tab.setObjectName("api_tab")
        
        tabs.addTab(basic_tab, "基本设置")
        tabs.addTab(repo_tab, "仓库管理")
        tabs.addTab(api_tab, "API 设置")
        
        layout.addWidget(tabs)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        save_btn = QPushButton("💾 保存")
        save_btn.setObjectName("save_btn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_config)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("background-color: #888;")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def auto_fill_defaults(self):
        """自动填充默认路径"""
        if not self.steam_path_edit.text():
            if os.path.exists(DEFAULT_STEAM_PATH):
                self.steam_path_edit.setText(DEFAULT_STEAM_PATH)
        
        steam_path = self.steam_path_edit.text()
        if steam_path and not self.lua_path_edit.text():
            lua_path = os.path.join(steam_path, "config", "stplug-in")
            if os.path.exists(lua_path):
                self.lua_path_edit.setText(lua_path)
    
    def load_repositories(self):
        """加载仓库列表"""
        self.repo_list.clear()
        repos = self.config.get("repositories", [])
        
        # 添加本地仓库
        local_path = self.config.get("manifest_repo_path", "")
        if local_path:
            item = QListWidgetItem(f"📁 [本地] {local_path}")
            self.repo_list.addItem(item)
        
        # 添加远程仓库
        for repo in repos:
            if repo.get("type") == "remote":
                url = repo.get("url", repo.get("path", ""))
                name = repo.get("name", "未命名")
                enabled = "✓" if repo.get("enabled", True) else "✗"
                item = QListWidgetItem(f"🌐 [{enabled}] {name}: {url}")
                self.repo_list.addItem(item)
        
        # 如果没有仓库，显示默认 GitHub
        if self.repo_list.count() == 0:
            item = QListWidgetItem(f"🌐 [默认] ManifestHub: {GITHUB_REPO_URL}")
            self.repo_list.addItem(item)
    
    def create_basic_tab(self) -> QWidget:
        """创建基本设置选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Steam 路径
        steam_group = QGroupBox("Steam 路径")
        steam_layout = QHBoxLayout()
        self.steam_path_edit = QLineEdit(self.config.get("steam_path", ""))
        self.steam_path_edit.setPlaceholderText("例如: C:/Program Files (x86)/Steam")
        steam_browse_btn = QPushButton("📁 浏览")
        steam_browse_btn.clicked.connect(self.browse_steam_path)
        steam_layout.addWidget(self.steam_path_edit, 1)
        steam_layout.addWidget(steam_browse_btn)
        steam_group.setLayout(steam_layout)
        
        # Lua 脚本目录
        lua_group = QGroupBox("Lua 脚本目录 (stplug-in)")
        lua_layout = QHBoxLayout()
        self.lua_path_edit = QLineEdit(self.config.get("lua_path", ""))
        self.lua_path_edit.setPlaceholderText("例如: C:/Program Files (x86)/Steam/config/stplug-in")
        lua_browse_btn = QPushButton("📁 浏览")
        lua_browse_btn.clicked.connect(self.browse_lua_path)
        lua_layout.addWidget(self.lua_path_edit, 1)
        lua_layout.addWidget(lua_browse_btn)
        lua_group.setLayout(lua_layout)
        
        # 视图模式
        view_group = QGroupBox("显示设置")
        view_layout = QHBoxLayout()
        view_label = QLabel("默认视图:")
        self.view_mode_combo = QComboBox()
        self.view_mode_combo.addItems(["网格视图", "列表视图"])
        current_mode = self.config.get("view_mode", "grid")
        self.view_mode_combo.setCurrentIndex(0 if current_mode == "grid" else 1)
        
        tool_label = QLabel("    解锁工具:")
        self.tool_combo = QComboBox()
        self.tool_combo.addItems(["SteamTools", "GreenLuma"])
        current_tool = self.config.get("preferred_unlock_tool", "steamtools")
        self.tool_combo.setCurrentIndex(0 if current_tool == "steamtools" else 1)
        
        view_layout.addWidget(view_label)
        view_layout.addWidget(self.view_mode_combo)
        view_layout.addWidget(tool_label)
        view_layout.addWidget(self.tool_combo)
        view_layout.addStretch()
        view_group.setLayout(view_layout)
        
        # 解锁源设置
        source_group = QGroupBox("解锁源设置")
        source_layout = QHBoxLayout()
        source_label = QLabel("首选仓库:")
        self.source_combo = QComboBox()
        self.source_combo.addItems(["远程 (GitHub) - 推荐", "本地 (Git仓库)"])
        source_layout.addWidget(source_label)
        source_layout.addWidget(self.source_combo)
        
        # 初始选择
        unlock_source = self.config.get("unlock_source", "remote")
        self.source_combo.setCurrentIndex(0 if unlock_source == "remote" else 1)
        
        source_layout.addStretch()
        source_group.setLayout(source_layout)

        
        # 数据隐私
        privacy_group = QGroupBox("数据隐私")
        privacy_layout = QVBoxLayout()
        self.save_names_check = QCheckBox("保存游戏名称 (关闭以仅显示 AppID)")
        self.save_names_check.setChecked(self.config.get("save_game_names", False))
        
        self.save_extra_check = QCheckBox("保存详细数据 (密钥、清单 ID 等)")
        self.save_extra_check.setChecked(self.config.get("save_extra_data", False))
        
        privacy_layout.addWidget(self.save_names_check)
        privacy_layout.addWidget(self.save_extra_check)
        privacy_group.setLayout(privacy_layout)
        
        layout.addWidget(steam_group)
        layout.addWidget(lua_group)
        layout.addWidget(view_group)
        layout.addWidget(source_group)

        layout.addWidget(privacy_group)

        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
    
    def create_repo_tab(self) -> QWidget:
        """创建仓库管理选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 本地仓库
        local_group = QGroupBox("本地仓库")
        local_layout = QVBoxLayout()
        
        local_input = QHBoxLayout()
        self.local_repo_edit = QLineEdit(self.config.get("manifest_repo_path", ""))
        self.local_repo_edit.setPlaceholderText("选择本地 Git 仓库路径 (可选)")
        local_browse_btn = QPushButton("📁 浏览")
        local_browse_btn.clicked.connect(self.browse_repo_path)
        local_input.addWidget(self.local_repo_edit, 1)
        local_input.addWidget(local_browse_btn)
        
        local_layout.addLayout(local_input)
        local_group.setLayout(local_layout)
        
        # 远程仓库
        remote_group = QGroupBox("远程仓库")
        remote_layout = QVBoxLayout()
        
        # 添加 URL 输入
        add_layout = QHBoxLayout()
        self.remote_url_edit = QLineEdit()
        self.remote_url_edit.setPlaceholderText("输入 GitHub 仓库 URL，例如: https://github.com/user/repo")
        add_btn = QPushButton("➕ 添加")
        add_btn.clicked.connect(self.add_remote_repo)
        add_layout.addWidget(self.remote_url_edit, 1)
        add_layout.addWidget(add_btn)
        
        # 仓库列表
        self.repo_list = QListWidget()
        self.repo_list.setMinimumHeight(120)
        
        # 删除按钮
        remove_btn = QPushButton("🗑️ 删除选中")
        remove_btn.setStyleSheet("background-color: #d9534f;")
        remove_btn.clicked.connect(self.remove_selected_repo)
        
        remote_layout.addLayout(add_layout)
        remote_layout.addWidget(QLabel("已配置的仓库:"))
        remote_layout.addWidget(self.repo_list)
        remote_layout.addWidget(remove_btn)
        remote_group.setLayout(remote_layout)
        
        # 提示
        hint = QLabel(f"💡 默认远程仓库: {GITHUB_REPO_URL}")
        hint.setStyleSheet("color: #666; font-size: 11px;")
        
        layout.addWidget(local_group)
        layout.addWidget(remote_group)
        layout.addWidget(hint)
        
        widget.setLayout(layout)
        return widget
    
    def create_api_tab(self) -> QWidget:
        """创建 API 设置选项卡"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # ManifestHub API
        api_group = QGroupBox("ManifestHub API")
        api_layout = QVBoxLayout()
        
        info_label = QLabel(
            "API 用于获取最新的 manifest 文件\n"
            "获取免费 API 密钥: https://manifesthub1.filegear-sg.me\n"
            "免费密钥有效期 24 小时"
        )
        info_label.setStyleSheet("color: #666; font-size: 11px;")
        
        key_layout = QHBoxLayout()
        key_label = QLabel("API 密钥:")
        self.api_key_edit = QLineEdit(self.config.get("api_key", ""))
        self.api_key_edit.setPlaceholderText("输入您的 API 密钥")
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        
        self.show_key_btn = QPushButton("👁")
        self.show_key_btn.setFixedWidth(40)
        self.show_key_btn.clicked.connect(self.toggle_api_key_visibility)
        
        validate_btn = QPushButton("✓ 验证")
        validate_btn.clicked.connect(self.validate_api_key)
        
        key_layout.addWidget(key_label)
        key_layout.addWidget(self.api_key_edit, 1)
        key_layout.addWidget(self.show_key_btn)
        key_layout.addWidget(validate_btn)
        
        api_layout.addWidget(info_label)
        api_layout.addLayout(key_layout)
        api_group.setLayout(api_layout)
        
        # GitHub Token
        github_group = QGroupBox("GitHub Token (高并发请求)")
        github_layout = QVBoxLayout()
        
        github_info = QLabel(
            "配置 GitHub Token 可将 API 限制从 60次/小时 提升到 5000次/小时\n"
            "用于：获取分支列表、下载清单、批量解锁等高并发任务\n"
            "获取: GitHub → Settings → Developer settings → Personal access tokens"
        )
        github_info.setStyleSheet("color: #666; font-size: 11px;")
        
        github_key_layout = QHBoxLayout()
        github_label = QLabel("Token:")
        self.github_token_edit = QLineEdit(self.config.get("github_token", ""))
        self.github_token_edit.setPlaceholderText("ghp_xxxxxxxxxxxx")
        self.github_token_edit.setEchoMode(QLineEdit.Password)
        
        self.show_github_btn = QPushButton("👁")
        self.show_github_btn.setFixedWidth(40)
        self.show_github_btn.clicked.connect(self.toggle_github_token_visibility)
        
        github_key_layout.addWidget(github_label)
        github_key_layout.addWidget(self.github_token_edit, 1)
        github_key_layout.addWidget(self.show_github_btn)
        
        github_layout.addWidget(github_info)
        github_layout.addLayout(github_key_layout)
        github_group.setLayout(github_layout)
        
        layout.addWidget(api_group)
        layout.addWidget(github_group)
        layout.addStretch()
        
        widget.setLayout(layout)
        return widget
    
    def toggle_github_token_visibility(self):
        """切换 GitHub Token 可见性"""
        if self.github_token_edit.echoMode() == QLineEdit.Password:
            self.github_token_edit.setEchoMode(QLineEdit.Normal)
            self.show_github_btn.setText("🙈")
        else:
            self.github_token_edit.setEchoMode(QLineEdit.Password)
            self.show_github_btn.setText("👁")

    
    def add_remote_repo(self):
        """添加远程仓库"""
        url = self.remote_url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "输入错误", "请输入仓库 URL")
            return
        
        if not url.startswith("https://"):
            QMessageBox.warning(self, "URL 格式错误", "请输入有效的 HTTPS URL")
            return
        
        # 从 URL 提取仓库名
        name = url.rstrip("/").split("/")[-1]
        if name.endswith(".git"):
            name = name[:-4]
        
        # 添加到配置
        repos = self.config.get("repositories", [])
        repos.append({
            "name": name,
            "type": "remote",
            "url": url,
            "enabled": True
        })
        self.config["repositories"] = repos
        
        # 更新列表
        self.load_repositories()
        self.remote_url_edit.clear()
        
        QMessageBox.information(self, "添加成功", f"已添加仓库: {name}")
    
    def remove_selected_repo(self):
        """删除选中的仓库"""
        current = self.repo_list.currentItem()
        if not current:
            QMessageBox.warning(self, "未选中", "请先选择要删除的仓库")
            return
        
        text = current.text()
        
        # 检查是否是本地仓库
        if "[本地]" in text:
            self.local_repo_edit.clear()
            self.config["manifest_repo_path"] = ""
        elif "[默认]" in text:
            QMessageBox.information(self, "无法删除", "默认仓库无法删除")
            return
        else:
            # 删除远程仓库
            repos = self.config.get("repositories", [])
            new_repos = []
            for repo in repos:
                url = repo.get("url", repo.get("path", ""))
                if url not in text:
                    new_repos.append(repo)
            self.config["repositories"] = new_repos
        
        self.load_repositories()
    
    def browse_steam_path(self):
        """浏览 Steam 路径"""
        initial = self.steam_path_edit.text() or DEFAULT_STEAM_PATH
        path = QFileDialog.getExistingDirectory(self, "选择Steam安装目录", initial)
        if path:
            self.steam_path_edit.setText(os.path.normpath(path))
            lua_path = os.path.join(path, "config", "stplug-in")
            if os.path.exists(lua_path) and not self.lua_path_edit.text():
                self.lua_path_edit.setText(lua_path)
    
    def browse_repo_path(self):
        """浏览本地仓库路径"""
        path = QFileDialog.getExistingDirectory(self, "选择清单仓库目录", self.local_repo_edit.text())
        if path:
            self.local_repo_edit.setText(os.path.normpath(path))
            self.load_repositories()
    
    def browse_lua_path(self):
        """浏览 Lua 目录"""
        initial = self.lua_path_edit.text()
        if not initial:
            steam_path = self.steam_path_edit.text()
            if steam_path:
                initial = os.path.join(steam_path, "config", "stplug-in")
        path = QFileDialog.getExistingDirectory(self, "选择stplug-in目录", initial)
        if path:
            self.lua_path_edit.setText(os.path.normpath(path))
    
    def toggle_api_key_visibility(self):
        """切换 API 密钥可见性"""
        if self.api_key_edit.echoMode() == QLineEdit.Password:
            self.api_key_edit.setEchoMode(QLineEdit.Normal)
            self.show_key_btn.setText("🔒")
        else:
            self.api_key_edit.setEchoMode(QLineEdit.Password)
            self.show_key_btn.setText("👁")
    
    def validate_api_key(self):
        """验证 API 密钥 - 后台线程执行避免阻塞 UI"""
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QMessageBox.warning(self, "验证失败", "请输入 API 密钥")
            return
        
        # 禁用验证按钮防止重复点击
        self._validate_btn = self.sender()
        if self._validate_btn:
            self._validate_btn.setEnabled(False)
            self._validate_btn.setText("验证中...")
        
        # 连接信号（一次性连接）
        try:
            self._validationResult.disconnect()
        except:
            pass
        self._validationResult.connect(self._on_validation_result)
        
        import threading
        
        def do_validate():
            try:
                from models.ManifestHub_API_model import ManifestHubAPI
                api = ManifestHubAPI(api_key)
                valid, message = api.validate_api_key()
                # 发射信号到主线程
                self._validationResult.emit(valid, message)
            except Exception as e:
                self._validationResult.emit(False, f"验证时出错: {e}")
        
        threading.Thread(target=do_validate, daemon=True).start()
    
    def _on_validation_result(self, valid: bool, message: str):
        """处理验证结果（在主线程中执行）"""
        # 恢复按钮状态
        if hasattr(self, '_validate_btn') and self._validate_btn:
            self._validate_btn.setEnabled(True)
            self._validate_btn.setText("✓ 验证")
        
        # 显示结果
        if valid:
            QMessageBox.information(self, "验证成功", "✓ API 密钥有效！")
        else:
            QMessageBox.warning(self, "验证失败", f"✗ {message}")
    
    def save_config(self):
        """保存配置"""
        steam_path = self.steam_path_edit.text().strip()
        local_repo = self.local_repo_edit.text().strip()
        lua_path = self.lua_path_edit.text().strip()
        api_key = self.api_key_edit.text().strip()
        
        # 标准化路径
        if steam_path:
            steam_path = os.path.normpath(steam_path)
        if local_repo:
            local_repo = os.path.normpath(local_repo)
        if lua_path:
            lua_path = os.path.normpath(lua_path)
        
        # Steam 路径是必须的
        if not steam_path:
            QMessageBox.warning(self, "输入错误", "请输入Steam路径")
            return
        
        if not os.path.exists(steam_path):
            result = QMessageBox.question(
                self, "路径不存在", 
                f"Steam路径 '{steam_path}' 不存在，是否继续?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.No:
                return
        
        # 如果填了本地仓库，检查有效性
        if local_repo:
            git_dir = os.path.join(local_repo, ".git")
            if not os.path.exists(git_dir):
                result = QMessageBox.warning(
                    self, "无效仓库", 
                    f"指定路径不是有效的Git仓库，是否继续?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if result == QMessageBox.No:
                    return
        
        # 更新配置
        self.config["steam_path"] = steam_path
        self.config["manifest_repo_path"] = local_repo
        self.config["lua_path"] = lua_path
        self.config["api_key"] = api_key
        self.config["github_token"] = self.github_token_edit.text().strip()
        self.config["view_mode"] = "grid" if self.view_mode_combo.currentIndex() == 0 else "list"
        self.config["preferred_unlock_tool"] = "steamtools" if self.tool_combo.currentIndex() == 0 else "greenluma"
        self.config["unlock_source"] = "remote" if self.source_combo.currentIndex() == 0 else "local"
        self.config["save_game_names"] = self.save_names_check.isChecked()
        self.config["save_extra_data"] = self.save_extra_check.isChecked()


        
        self.configSaved.emit(self.config)
        self.accept()

    def set_theme(self, theme_name):
        """设置对话框主题"""
        if theme_name == "dark":
            self.setStyleSheet(self.DARK_STYLE)
        else:
            self.setStyleSheet(self.LIGHT_STYLE)
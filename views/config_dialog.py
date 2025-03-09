import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal

class ConfigDialog(QDialog):
    """配置对话框，用于设置应用程序所需的路径"""
    
    # 定义信号，用于通知配置已保存
    configSaved = pyqtSignal(dict)
    
    def __init__(self, parent=None, config=None):
        """初始化配置对话框
        
        Args:
            parent: 父窗口
            config: 当前配置字典，包含steam_path和manifest_repo_path
        """
        super().__init__(parent)
        self.config = config or {"steam_path": "", "manifest_repo_path": "", "preferred_unlock_tool": "steamtools"}
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI界面"""
        self.setWindowTitle("Steam游戏解锁器 - 配置")
        self.setMinimumWidth(500)
        self.setMinimumHeight(200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout()
        
        # 1. Steam路径设置
        steam_layout = QHBoxLayout()
        steam_label = QLabel("Steam路径:")
        self.steam_path_edit = QLineEdit(self.config.get("steam_path", ""))
        self.steam_path_edit.setPlaceholderText("例如: C:/Program Files (x86)/Steam")
        steam_browse_btn = QPushButton("浏览...")
        steam_browse_btn.clicked.connect(self.browse_steam_path)
        
        steam_layout.addWidget(steam_label)
        steam_layout.addWidget(self.steam_path_edit, 1)
        steam_layout.addWidget(steam_browse_btn)
        
        # 2. 清单仓库路径设置
        repo_layout = QHBoxLayout()
        repo_label = QLabel("清单仓库路径:")
        self.repo_path_edit = QLineEdit(self.config.get("manifest_repo_path", ""))
        self.repo_path_edit.setPlaceholderText("例如: D:/Game/steamtools/Manifes/SteamAutoCracks/ManifestHub")
        repo_browse_btn = QPushButton("浏览...")
        repo_browse_btn.clicked.connect(self.browse_repo_path)
        
        repo_layout.addWidget(repo_label)
        repo_layout.addWidget(self.repo_path_edit, 1)
        repo_layout.addWidget(repo_browse_btn)
        
        # 3. 帮助信息
        help_text = QLabel(
            "注意: 请确保Steam路径指向Steam的安装目录，清单仓库路径指向一个有效的Git仓库目录。\n"
            "如果没有清单仓库，请先克隆 https://github.com/SteamAutoCracks/ManifestHub 到本地。"
        )
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666; font-size: 11px;")
        
        # 4. 按钮区域
        button_layout = QHBoxLayout()
        save_btn = QPushButton("保存")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.save_config)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addStretch()
        button_layout.addWidget(save_btn)
        button_layout.addWidget(cancel_btn)
        
        # 添加所有组件到主布局
        layout.addLayout(steam_layout)
        layout.addLayout(repo_layout)
        layout.addWidget(help_text)
        layout.addStretch()
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def browse_steam_path(self):
        """浏览并选择Steam路径"""
        path = QFileDialog.getExistingDirectory(
            self, "选择Steam安装目录", self.steam_path_edit.text()
        )
        if path:
            # 标准化路径格式
            path = os.path.normpath(path)
            self.steam_path_edit.setText(path)
    
    def browse_repo_path(self):
        """浏览并选择清单仓库路径"""
        path = QFileDialog.getExistingDirectory(
            self, "选择清单仓库目录", self.repo_path_edit.text()
        )
        if path:
            # 标准化路径格式
            path = os.path.normpath(path)
            self.repo_path_edit.setText(path)
    
    def save_config(self):
        """保存配置"""
        steam_path = self.steam_path_edit.text().strip()
        repo_path = self.repo_path_edit.text().strip()
        
        # 标准化路径格式，确保反斜杠被正确处理
        steam_path = os.path.normpath(steam_path)
        repo_path = os.path.normpath(repo_path)
        
        # 验证路径
        if not steam_path:
            QMessageBox.warning(self, "输入错误", "请输入Steam路径")
            return
        
        if not repo_path:
            QMessageBox.warning(self, "输入错误", "请输入清单仓库路径")
            return
        
        # 检查路径是否存在
        if not os.path.exists(steam_path):
            result = QMessageBox.question(
                self, 
                "路径不存在", 
                f"Steam路径 '{steam_path}' 不存在，是否继续?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.No:
                return
        
        if not os.path.exists(repo_path):
            result = QMessageBox.question(
                self, 
                "路径不存在", 
                f"清单仓库路径 '{repo_path}' 不存在，是否继续?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.No:
                return
        
        # 检查清单仓库是否为Git仓库
        git_dir = os.path.join(repo_path, ".git")
        if os.path.exists(repo_path) and not os.path.exists(git_dir):
            result = QMessageBox.warning(
                self, 
                "无效仓库", 
                f"指定的清单仓库路径不是一个有效的Git仓库，请确保该路径包含.git目录。\n\n是否继续?",
                QMessageBox.Yes | QMessageBox.No
            )
            if result == QMessageBox.No:
                return
        
        # 更新配置
        self.config["steam_path"] = steam_path
        self.config["manifest_repo_path"] = repo_path
        
        # 发出信号并关闭对话框
        self.configSaved.emit(self.config)
        self.accept() 
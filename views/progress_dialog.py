"""非阻塞进度弹窗 - 显示下载进度而不阻塞主界面"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                             QProgressBar, QPushButton, QTextEdit)
from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QFont


class ProgressDialog(QDialog):
    """非模态进度弹窗，不阻塞主界面"""
    
    # 信号用于线程安全更新
    progressUpdated = pyqtSignal(int, int, str)  # current, total, message
    logAppended = pyqtSignal(str)  # log message
    finished = pyqtSignal(bool, str)  # success, final message
    
    def __init__(self, parent=None, title="下载进度"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(500, 300)
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        
        # 不阻塞主窗口
        self.setModal(False)
        
        self.setup_ui()
        self.connect_signals()
        
        self._is_cancelled = False
    
    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 标题标签
        self.title_label = QLabel("正在处理...")
        self.title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        layout.addWidget(self.title_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%v / %m (%p%)")
        layout.addWidget(self.progress_bar)
        
        # 状态标签
        self.status_label = QLabel("准备中...")
        layout.addWidget(self.status_label)
        
        # 统计信息
        stats_layout = QHBoxLayout()
        self.success_label = QLabel("成功: 0")
        self.success_label.setStyleSheet("color: green; font-weight: bold;")
        self.fail_label = QLabel("失败: 0")
        self.fail_label.setStyleSheet("color: red; font-weight: bold;")
        self.speed_label = QLabel("速度: 0/s")
        self.time_label = QLabel("耗时: 0s")
        
        stats_layout.addWidget(self.success_label)
        stats_layout.addWidget(self.fail_label)
        stats_layout.addWidget(self.speed_label)
        stats_layout.addWidget(self.time_label)
        stats_layout.addStretch()
        layout.addLayout(stats_layout)
        
        # 日志区域
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(120)
        self.log_text.setStyleSheet("font-family: Consolas; font-size: 11px;")
        layout.addWidget(self.log_text)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setEnabled(False)  # 完成后才能关闭
        btn_layout.addWidget(self.close_btn)
        
        layout.addLayout(btn_layout)
        
        # 统计变量
        self._success_count = 0
        self._fail_count = 0
        self._start_time = 0
    
    def connect_signals(self):
        """连接信号"""
        self.progressUpdated.connect(self._on_progress_updated)
        self.logAppended.connect(self._on_log_appended)
        self.finished.connect(self._on_finished)
    
    def start(self, total: int, title: str = "正在处理..."):
        """开始进度跟踪"""
        import time
        self._start_time = time.time()
        self._success_count = 0
        self._fail_count = 0
        self._is_cancelled = False
        
        self.title_label.setText(title)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.status_label.setText("正在下载...")
        self.close_btn.setEnabled(False)
        self.log_text.clear()
        
        self.show()
        self.raise_()
    
    @pyqtSlot(int, int, str)
    def _on_progress_updated(self, current: int, total: int, message: str):
        """更新进度"""
        import time
        
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(message)
        
        # 计算速度和耗时
        elapsed = time.time() - self._start_time
        speed = current / elapsed if elapsed > 0 else 0
        
        self.speed_label.setText(f"速度: {speed:.1f}/s")
        self.time_label.setText(f"耗时: {elapsed:.0f}s")
    
    def update_stats(self, success: int, fail: int):
        """更新统计信息（线程安全）"""
        self._success_count = success
        self._fail_count = fail
        # 使用 QTimer 确保在主线程更新 UI
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(0, self._refresh_stats)
    
    def _refresh_stats(self):
        """刷新统计显示"""
        self.success_label.setText(f"成功: {self._success_count}")
        self.fail_label.setText(f"失败: {self._fail_count}")
    
    @pyqtSlot(str)
    def _on_log_appended(self, message: str):
        """追加日志"""
        self.log_text.append(message)
        # 滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    @pyqtSlot(bool, str)
    def _on_finished(self, success: bool, message: str):
        """完成处理"""
        import time
        elapsed = time.time() - self._start_time
        
        if success:
            self.title_label.setText("✅ 完成")
            self.title_label.setStyleSheet("color: green;")
        else:
            self.title_label.setText("❌ 失败")
            self.title_label.setStyleSheet("color: red;")
        
        self.status_label.setText(message)
        self.time_label.setText(f"总耗时: {elapsed:.1f}s")
        self.close_btn.setEnabled(True)
        
        # 追加完成日志
        self.log_text.append(f"\n{'='*40}")
        self.log_text.append(message)
    
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self._is_cancelled
    
    def closeEvent(self, event):
        """关闭事件"""
        if not self.close_btn.isEnabled():
            # 下载中，标记取消
            self._is_cancelled = True
        event.accept()

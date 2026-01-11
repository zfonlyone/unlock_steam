import sys
import os
import json
import queue
import asyncio
from PyQt5.QtWidgets import QApplication, QMessageBox, QSplashScreen
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import QTimer, Qt

# 导入MVC组件
from models import DataManager, UnlockModel, GitModel, ConfigModel
from models.steam_api_model import SteamApiModel
from models.project_info import project_info
from views import MainWindow, ConfigDialog
from views.progress_dialog import ProgressDialog
from controllers import SearchController, UnlockController, GitController, SteamApiController
from controllers.menu_manager import MenuManager

import threading
import time

class App:
    """应用程序类，负责初始化和协调MVC组件"""
    
    def __init__(self):
        # 先验证项目完整性
        self.verify_project_integrity()
        
        # 创建配置模型
        self.config_model = ConfigModel()
        
        # 创建数据模型
        self.data_manager = DataManager(config_model=self.config_model)
        
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
        
        # 连接关于请求信号
        self.main_window.aboutRequested.connect(self.show_about_dialog)
        
        # 创建控制器组件
        self.search_controller = SearchController(self.data_manager, self.main_window)
        self.unlock_controller = UnlockController(self.data_manager, self.unlock_model, self.config_model, self.main_window)
        self.git_controller = GitController(self.data_manager, self.git_model, self.config_model, self.main_window)
        
        self.steam_api_controller = SteamApiController(
            steam_api_model=self.steam_api_model,
            data_model=self.data_manager,
            config_model=self.config_model,
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
        self.unlock_controller.batchUnlockCompleted.connect(self.handle_batch_results)
        
        # 连接Steam API控制器信号
        self.main_window.fetchGameNamesRequested.connect(self.steam_api_controller.fetch_all_game_names)
        
        # 一键解锁相关变量
        self.batch_unlock_queue = queue.Queue()
        self.is_batch_unlocking = False
        self.batch_unlock_thread = None
        
        # 连接一键解锁信号
        self.main_window.batchUnlockRequested.connect(self.start_batch_unlock)
        
        # 启动UI守护线程
        self.start_ui_guardian()
        
        # 延迟加载数据
        QTimer.singleShot(100, self.load_initial_data)
    
    def verify_project_integrity(self):
        """验证项目完整性，防止被篡改"""
        # 如果检测到篡改，显示警告并退出
        if project_info.detect_runtime_tampering():
            QMessageBox.critical(
                None,
                "安全警告",
                "程序文件已被篡改或损坏，为保证安全，程序将退出。\n"
                "请重新下载原版程序。"
            )
            sys.exit(1)
    
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
        print("UI守护线程已启动")
    
    def check_and_restore_ui(self):
        """检查并恢复UI状态"""
        try:
            # 恢复按钮状态
            self.main_window.enable_buttons(True)
            # 处理挂起的事件
            QApplication.processEvents()
            print("UI守护：已检查并恢复UI状态")
        except Exception as e:
            print(f"UI守护：恢复UI状态失败: {e}")
    
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
    
    def show_about_dialog(self):
        """显示关于对话框"""
        QMessageBox.about(
            self.main_window,
            f"关于 {project_info.get_app_name()}",
            project_info.get_about_info()
        )
    
    def scan_unlocked_games(self):
        """扫描未解锁游戏，返回appid列表"""
        all_games = self.data_manager.get_all_games()
        
        # 创建事件循环来获取已解锁游戏列表
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        unlocked_games = loop.run_until_complete(self.unlock_model.scan_unlocked_games())
        loop.close()
        
        # 转换已解锁游戏为set，便于快速查找
        unlocked_set = set(unlocked_games.keys())
        
        # 找出未解锁的游戏
        unlocked_appids = []
        for game in all_games:
            app_id = game.get('app_id')
            if app_id and app_id not in unlocked_set:
                unlocked_appids.append(app_id)
        
        return unlocked_appids
    
    def start_batch_unlock(self):
        """开始批量解锁游戏"""
        if self.is_batch_unlocking:
            QMessageBox.information(
                self.main_window,
                "任务正在进行",
                "批量解锁任务正在进行中，请等待完成。"
            )
            return
        
        # 扫描未解锁游戏
        unlocked_appids = self.scan_unlocked_games()
        
        if not unlocked_appids:
            QMessageBox.information(
                self.main_window,
                "无需解锁",
                "没有需要解锁的游戏。"
            )
            return
        
        # 确认是否解锁
        reply = QMessageBox.question(
            self.main_window,
            "确认解锁",
            f"将要解锁 {len(unlocked_appids)} 个游戏，是否继续？\n这个过程将在后台进行，您可以继续使用其他功能。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )
        
        if reply == QMessageBox.No:
            return
        
        # 准备队列
        for app_id in unlocked_appids:
            self.batch_unlock_queue.put(app_id)
        
        # 设置标志
        self.is_batch_unlocking = True
        
        # 更新状态
        self.main_window.set_status(f"开始批量解锁 {len(unlocked_appids)} 个游戏...")
        
        # 启动解锁线程
        self.batch_unlock_thread = threading.Thread(target=self.batch_unlock_worker)
        self.batch_unlock_thread.daemon = True
        self.batch_unlock_thread.start()
    
    def batch_unlock_worker(self):
        """批量解锁工作线程 - 并发版本
        
        使用 Go 下载器或 Python asyncio 实现高并发解锁
        - Go 下载器: 100 并发任务
        - Python 回退: 50 并发任务
        """
        # 收集所有待解锁的 app_ids
        app_ids = []
        while not self.batch_unlock_queue.empty():
            try:
                app_id = self.batch_unlock_queue.get(block=False)
                app_ids.append(app_id)
                self.batch_unlock_queue.task_done()
            except queue.Empty:
                break
        
        total_games = len(app_ids)
        if total_games == 0:
            print("没有待解锁的游戏")
            self.is_batch_unlocking = False
            return
        
        print(f"\n{'='*60}")
        print(f"🚀 批量解锁开始，总计 {total_games} 个游戏 (并发模式)")
        print(f"{'='*60}\n")
        QTimer.singleShot(0, lambda: self.main_window.set_status(f"准备并发解锁 {total_games} 个游戏..."))
        
        # 创建非阻塞进度弹窗
        self._progress_dialog = ProgressDialog(self.main_window, "一键解锁")
        self._progress_dialog.start(total_games, f"正在解锁 {total_games} 个游戏...")
        
        # 进度条状态
        self._progress_state = {"last_percent": -1, "start_time": time.time()}
        
        def print_progress_bar(percent, msg=""):
            """打印 ASCII 进度条"""
            # 如果 percent 为 -1，则保持上次的进度，只更新消息
            if percent == -1:
                percent = max(0, self._progress_state["last_percent"])
            
            bar_width = 40
            filled = int(bar_width * percent / 100)
            bar = "█" * filled + "░" * (bar_width - filled)
            elapsed = time.time() - self._progress_state["start_time"]
            
            # 记录进度
            self._progress_state["last_percent"] = percent
            # 使用 \r 覆盖当前行，放宽截断限制以显示完整 URL
            clean_msg = msg[:150].ljust(150)
            print(f"\r[{bar}] {percent:3d}% | {elapsed:.1f}s | {clean_msg}", end="", flush=True)
            if percent >= 100:
                print()  # 完成时换行
        
        try:
            # 创建事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 进度回调
            def progress_callback(msg, percent):
                self.unlock_controller.progressUpdated.emit(msg, percent)
                print_progress_bar(percent, msg)
                
                # 更新进度弹窗
                if percent >= 0:
                    completed = int(total_games * percent / 100)
                    self._progress_dialog.progressUpdated.emit(completed, total_games, msg[:80])
            
            # 从外部模型构建 AppID -> ManifestIDs 的映射
            # 这样 Go 下载器就不需要通过 API 就能知道要下哪些清单了
            app_data = {}
            all_games = self.data_manager.get_all_games()
            game_map = {str(g['app_id']): g for g in all_games}
            
            for aid in app_ids:
                game = game_map.get(str(aid))
                if game and 'depots' in game:
                    # 提取该游戏下所有的 manifest_id (包含 DepotID 用于精确匹配)
                    m_ids = [f"{did}_{d['manifest_id']}" for did, d in game['depots'].items() if d.get('manifest_id')]
                    if m_ids:
                        app_data[str(aid)] = m_ids

            # 使用并发解锁方法
            results = loop.run_until_complete(
                self.unlock_model.batch_unlock_concurrent(app_ids, progress_callback, app_data=app_data)
            )
            loop.close()
            
            # 统计结果
            success_count = sum(1 for s, _ in results.values() if s)
            fail_count = len(results) - success_count
            elapsed = time.time() - self._progress_state["start_time"]
            
            # 收集失败的 AppID 和原因
            failed_ids = [(app_id, message) for app_id, (success, message) in results.items() if not success]
            
            # 更新数据库中的解锁状态
            for app_id, (success, message) in results.items():
                if success:
                    self.data_manager.set_unlock_status(app_id, True, auto_save=False)
            self.data_manager.save_to_json()  # 批量保存
            
            # 显示失败的 AppID 和原因
            if failed_ids:
                fail_log = f"失败的 AppID ({len(failed_ids)} 个):\n"
                for app_id, error in failed_ids[:30]:
                    fail_log += f"  {app_id}: {error}\n"
                if len(failed_ids) > 30:
                    fail_log += f"  ... 及其他 {len(failed_ids) - 30} 个"
                self._progress_dialog.logAppended.emit(fail_log)
                print(f"\n失败的 AppID:")
            
            # 显示最终结果
            print(f"\n{'='*60}")
            print(f"✅ 批量解锁完成！")
            print(f"   📊 成功: {success_count} | 失败: {fail_count} | 总计: {total_games}")
            print(f"   ⏱️  耗时: {elapsed:.1f} 秒 ({total_games/elapsed:.1f} 游戏/秒)" if elapsed > 0 else "")
            print(f"{'='*60}\n")
            
            # 更新进度弹窗
            final_msg = f"解锁完成！成功 {success_count} 个，失败 {fail_count} 个，耗时 {elapsed:.1f} 秒"
            self._progress_dialog.update_stats(success_count, fail_count)
            self._progress_dialog.finished.emit(success_count > 0, final_msg)
            
            self.unlock_controller.batchUnlockCompleted.emit(success_count, fail_count, total_games, elapsed)
            
        except Exception as e:
            error_msg = f"批量解锁出错: {e}"
            print(f"\n❌ {error_msg}")
            import traceback
            traceback.print_exc()
            
            # 更新进度弹窗显示错误
            self._progress_dialog.finished.emit(False, error_msg)
            
            self.unlock_controller.batchUnlockCompleted.emit(0, 0, 0, -1.0) # 发送错误信号
            QTimer.singleShot(0, lambda: self.main_window.set_status(f"出错: {error_msg}"))
        finally:
            # 重置标志
            self.is_batch_unlocking = False

    def handle_batch_results(self, success_count, fail_count, total_games, elapsed):
        """在主线程处理批量解锁结果"""
        if elapsed < 0:
            QMessageBox.critical(self.main_window, "批量解锁错误", "操作过程中发生严重异常，请检查日志。")
            return

        final_msg = f"✅ 批量解锁完成！成功: {success_count} | 失败: {fail_count} | 总计: {total_games}"
        self.main_window.set_status(final_msg)
        
        QMessageBox.information(
            self.main_window, 
            "批量操作完成", 
            f"解锁过程已结束：\n\n成功: {success_count}\n失败: {fail_count}\n总计: {total_games}\n耗时: {elapsed:.1f} 秒"
        )
        
        # 刷新界面
        self.main_window.refreshDisplayRequested.emit()
    
    def run(self):
        """运行应用程序"""
        # 添加版本信息到窗口标题
        app_title = f"{project_info.get_app_name()} v{project_info.get_version()}"
        self.main_window.setWindowTitle(app_title)
        
        # 显示主窗口
        self.main_window.show()

def main():
    """应用程序入口函数"""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # 设置应用程序风格
    

    
    # 创建并运行应用程序
    steam_app = App()
    

    
    # 运行应用
    steam_app.run()
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main() 
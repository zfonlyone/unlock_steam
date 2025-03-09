from typing import List, Dict, Any

class SearchController:
    """搜索功能控制器(Controller层)"""
    
    def __init__(self, model, view):
        """初始化控制器
        
        Args:
            model: 数据模型(DataManager)
            view: 视图(MainWindow)
        """
        self.model = model
        self.view = view
        
        # 连接视图信号到控制器方法
        self.view.searchRequested.connect(self.search)
        self.view.refreshDisplayRequested.connect(self.refresh_display)
    
    def search(self, query: str):
        """搜索游戏
        
        Args:
            query: 搜索关键词
        """
        if not query:
            # 如果搜索框为空，显示所有游戏
            self.refresh_display()
            self.view.set_status("显示所有游戏")
            return
            
        # 获取所有游戏
        all_games = self.model.get_all_games()
        
        # 如果查询是数字，优先尝试精确匹配AppID
        if query.isdigit():
            exact_matches = [game for game in all_games if game.get("app_id", "") == query]
            if exact_matches:
                self.view.update_table(exact_matches)
                self.view.set_status(f"找到AppID为 {query} 的游戏")
                return
        
        # 否则进行模糊搜索
        query = query.lower()
        filtered_games = []
        for game in all_games:
            app_id = game.get("app_id", "").lower()
            game_name = game.get("game_name", "").lower() if game.get("game_name") else ""
            
            if query in app_id or query in game_name:
                filtered_games.append(game)
        
        # 更新表格
        self.view.update_table(filtered_games)
        
        # 更新状态栏
        count = len(filtered_games)
        if count > 0:
            self.view.set_status(f"找到 {count} 个匹配的游戏")
        else:
            self.view.set_status("未找到匹配的游戏")
    
    def refresh_display(self):
        """刷新显示，从内存中加载数据但不改变数据"""
        all_games = self.model.get_all_games()
        self.view.update_table(all_games)
        
        # 更新状态栏
        if all_games:
            self.view.set_status(f"显示 {len(all_games)} 个游戏") 
        else:
            self.view.set_status("游戏列表为空，请点击'更新列表'按钮获取游戏数据") 
import requests
import random
import time
import json
import os
from typing import Dict, Optional, List, Tuple, Union


class SteamApiModel:
    """Steam API模型，负责与Steam API交互获取游戏信息"""
    
    def __init__(self):
        """初始化Steam API模型"""
        # API请求间隔控制
        self.last_request_time = 0
        self.min_request_interval = 1.0  # 最小请求间隔（秒）
        
        # 缓存已获取的游戏名称，减少重复请求
        self.name_cache_file = "steam_names_cache.json"
        self.names_cache = self._load_name_cache()
    
    def _load_name_cache(self) -> Dict[str, str]:
        """加载缓存的游戏名称数据
        
        Returns:
            Dict[str, str]: 游戏ID到名称的映射字典
        """
        if os.path.exists(self.name_cache_file):
            try:
                with open(self.name_cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载游戏名称缓存失败: {e}")
        return {}
    
    def _save_name_cache(self) -> None:
        """保存游戏名称缓存到文件"""
        try:
            with open(self.name_cache_file, "w", encoding="utf-8") as f:
                json.dump(self.names_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存游戏名称缓存失败: {e}")
    
    def _wait_for_rate_limit(self) -> None:
        """等待适当时间以避免请求过于频繁"""
        current_time = time.time()
        elapsed = current_time - self.last_request_time
        
        if elapsed < self.min_request_interval:
            # 等待至少达到最小间隔时间
            time.sleep(self.min_request_interval - elapsed + random.uniform(0, 0.5))
        
        # 更新最后请求时间
        self.last_request_time = time.time()
    
    def get_game_name(self, app_id: str, use_cache: bool = True) -> Tuple[bool, str]:
        """获取Steam游戏名称
        
        Args:
            app_id: 游戏AppID
            use_cache: 是否使用缓存数据，默认为True
            
        Returns:
            Tuple[bool, str]: (成功标志, 游戏名称或错误信息)
        """
        # 检查缓存
        if use_cache and app_id in self.names_cache:
            return True, self.names_cache[app_id]
        
        # 等待速率限制
        self._wait_for_rate_limit()
        
        # 构建Steam API URL
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=zh&cc=cn"
        
        # 随机选择User-Agent，模拟浏览器行为
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15'
        ]
        
        headers = {
            'User-Agent': random.choice(user_agents),
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        try:
            # 发送请求
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            # 解析响应
            data = response.json()
            app_data = data.get(str(app_id), {})
            
            # 检查API调用是否成功
            if not app_data.get('success', False):
                return False, f"API返回失败状态，无法获取游戏 {app_id} 的信息"
            
            # 提取游戏名称
            if 'data' not in app_data or 'name' not in app_data['data']:
                return False, f"API响应格式不正确，缺少游戏名称字段"
            
            game_name = app_data['data']['name']
            
            # 更新缓存
            self.names_cache[app_id] = game_name
            self._save_name_cache()
            
            return True, game_name
        
        except requests.exceptions.RequestException as e:
            return False, f"网络请求错误: {str(e)}"
        except json.JSONDecodeError as e:
            return False, f"JSON解析错误: {str(e)}"
        except Exception as e:
            return False, f"未知错误: {str(e)}"
    
    def get_multiple_game_names(self, app_ids: List[str], 
                               callback=None, 
                               use_cache: bool = True) -> Dict[str, str]:
        """批量获取游戏名称
        
        Args:
            app_ids: 游戏AppID列表
            callback: 处理每个游戏名称后的回调函数，接收(app_id, success, name, progress, total)
            use_cache: 是否使用缓存数据
        
        Returns:
            Dict[str, str]: 游戏ID到名称的映射字典（只包含成功获取的名称）
        """
        results = {}
        total = len(app_ids)
        
        for i, app_id in enumerate(app_ids):
            # 检查缓存
            if use_cache and app_id in self.names_cache:
                name = self.names_cache[app_id]
                results[app_id] = name
                if callback:
                    callback(app_id, True, name, i + 1, total)
                continue
            
            # 获取名称并处理回调
            success, name = self.get_game_name(app_id, use_cache=False)  # 避免双重缓存检查
            
            if success:
                results[app_id] = name
            
            if callback:
                callback(app_id, success, name, i + 1, total)
            
            # 添加随机延迟，避免请求过快
            time.sleep(random.uniform(0.5, 2.0))
        
        return results
    
    def get_game_details(self, app_id: str) -> Dict:
        """获取游戏的详细信息
        
        Args:
            app_id: 游戏AppID
            
        Returns:
            Dict: 游戏详细信息字典
        """
        # 等待速率限制
        self._wait_for_rate_limit()
        
        # 构建Steam API URL
        url = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=zh&cc=cn"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept-Language': 'zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            if app_id in data and data[app_id].get('success'):
                return data[app_id]['data']
            return {}
        except:
            return {} 
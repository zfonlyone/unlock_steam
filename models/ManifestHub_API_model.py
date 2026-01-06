"""
ManifestHub API 模型
封装远程 API 调用：获取 manifest、验证 API 密钥
API: https://api.manifesthub1.filegear-sg.me/manifest
"""
import requests
import time
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass


@dataclass
class ManifestInfo:
    """Manifest 信息"""
    depot_id: str
    manifest_id: str
    data: bytes = b''
    success: bool = False
    error: str = ""


class ManifestHubAPI:
    """ManifestHub API 封装"""
    
    BASE_URL = "https://api.manifesthub1.filegear-sg.me/manifest"
    GITHUB_RAW_URL = "https://raw.githubusercontent.com/SteamAutoCracks/ManifestHub"
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SteamGameUnlocker/2.0'
        })
    
    def set_api_key(self, api_key: str):
        """设置 API 密钥"""
        self.api_key = api_key
    
    def validate_api_key(self) -> Tuple[bool, str]:
        """验证 API 密钥是否有效
        
        Returns:
            (是否有效, 消息)
        """
        if not self.api_key:
            return False, "API 密钥不能为空"
        
        try:
            # 使用一个真实的测试请求验证密钥
            # 使用已知存在的 depot/manifest 作为测试
            response = self.session.get(
                self.BASE_URL,
                params={
                    'apikey': self.api_key,
                    'depotid': '2087471',  # 真实的 depot ID
                    'manifestid': '8648147806255524555'  # 真实的 manifest ID
                },
                timeout=30
            )
            
            # 尝试解析 JSON 响应
            try:
                data = response.json()
                
                # 检查响应中的 error 字段
                if 'error' in data:
                    error_msg = data.get('error', '')
                    if 'Invalid API key' in error_msg or 'invalid' in error_msg.lower():
                        return False, "API 密钥无效或已过期"
                    elif 'not found' in error_msg.lower() or 'manifest' in error_msg.lower():
                        # manifest 不存在但密钥有效
                        return True, "API 密钥有效"
                    else:
                        return False, f"API 错误: {error_msg}"
                
                # 如果有 success 字段
                if data.get('success') == True:
                    return True, "API 密钥有效"
                elif data.get('success') == False:
                    error_msg = data.get('error', '未知错误')
                    if 'key' in error_msg.lower():
                        return False, "API 密钥无效或已过期"
                    else:
                        # 其他错误（如 manifest 不存在）说明密钥是有效的
                        return True, "API 密钥有效"
                
                # 其他情况，假设成功
                return True, "API 密钥有效"
                
            except Exception:
                # 无法解析 JSON，根据状态码判断
                if response.status_code == 401 or response.status_code == 403:
                    return False, "API 密钥无效或已过期"
                elif response.status_code == 200:
                    return True, "API 密钥有效"
                else:
                    return False, f"未知响应: {response.status_code}"
                
        except requests.Timeout:
            return False, "连接超时"
        except requests.RequestException as e:
            return False, f"网络错误: {e}"
    
    def get_manifest(self, depot_id: str, manifest_id: str) -> ManifestInfo:
        """从 API 获取 manifest 文件
        
        Args:
            depot_id: Depot ID
            manifest_id: Manifest ID
            
        Returns:
            ManifestInfo 对象
        """
        result = ManifestInfo(
            depot_id=depot_id,
            manifest_id=manifest_id
        )
        
        if not self.api_key:
            result.error = "API 密钥未设置"
            return result
        
        try:
            response = self.session.get(
                self.BASE_URL,
                params={
                    'apikey': self.api_key,
                    'depotid': depot_id,
                    'manifestid': manifest_id
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result.data = response.content
                result.success = True
            elif response.status_code == 401:
                result.error = "API 密钥无效或已过期"
            elif response.status_code == 404:
                result.error = "Manifest 不存在"
            else:
                result.error = f"请求失败: {response.status_code}"
                
        except requests.Timeout:
            result.error = "请求超时"
        except requests.RequestException as e:
            result.error = f"网络错误: {e}"
        
        return result
    
    def get_manifest_batch(self, items: list) -> list:
        """批量获取 manifest
        
        Args:
            items: [(depot_id, manifest_id), ...]
            
        Returns:
            [ManifestInfo, ...]
        """
        results = []
        for depot_id, manifest_id in items:
            result = self.get_manifest(depot_id, manifest_id)
            results.append(result)
            # 避免请求过快
            time.sleep(0.1)
        return results
    
    def get_game_json_from_github(self, app_id: str, branch: str = "main") -> Optional[Dict[str, Any]]:
        """从 GitHub 获取游戏 JSON 信息
        
        Args:
            app_id: 游戏 AppID
            branch: 分支名称
            
        Returns:
            JSON 数据或 None
        """
        try:
            url = f"{self.GITHUB_RAW_URL}/{branch}/{app_id}.json"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None
    
    def list_branches_from_github(self) -> list:
        """从 GitHub API 获取所有分支列表
        
        Returns:
            分支名称列表
        """
        try:
            url = "https://api.github.com/repos/SteamAutoCracks/ManifestHub/branches"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                branches = response.json()
                return [b['name'] for b in branches if b['name'].isdigit()]
            return []
        except Exception:
            return []


# 单例模式
_api_instance: Optional[ManifestHubAPI] = None


def get_api(api_key: str = "") -> ManifestHubAPI:
    """获取 API 实例"""
    global _api_instance
    if _api_instance is None:
        _api_instance = ManifestHubAPI(api_key)
    elif api_key:
        _api_instance.set_api_key(api_key)
    return _api_instance

import hashlib
import hmac
import json
import os
import sys
import time
from typing import Dict, Any, Optional

class ProjectInfo:
    """项目信息管理类，存储和验证程序的基本信息，防止被篡改"""
    
    # 程序基本信息
    _PROJECT_INFO = {
        "name": "Steam游戏解锁工具",
        "name_en": "Steam Game Unlocker",
        "version": "1.2.0",
        "author": "zfonlyone",
        "license": "GPL-3.0",
        "description": "一个用于解锁Steam游戏的工具",
        "description_en": "A tool for unlocking Steam games",
        "website": "https://github.com/zfonlyone/unlock_steam",
        "build_date": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "copyright": f"Copyright © 2025 Your Name. All rights reserved."
    }
    
    # 密钥用于生成和验证签名 - 在实际部署时应使用更安全的方式存储
    _SECRET_KEY = b"c8e8105cc5de5ef9c8b1a2e5c8f7b5e1d5c7f9a5b2d5e8f1c5b9d2e5c8b1a5e9"
    
    def __init__(self):
        """初始化项目信息管理器"""
        self._info = self._PROJECT_INFO.copy()
        self._signature = self._generate_signature(self._info)
        
    def _generate_signature(self, data: Dict[str, Any]) -> str:
        """生成防篡改签名
        
        Args:
            data: 要签名的数据
            
        Returns:
            数据的签名
        """
        # 将数据转换为JSON字符串，按照键排序以确保一致性
        json_data = json.dumps(data, sort_keys=True)
        # 生成签名
        signature = hmac.new(
            self._SECRET_KEY,
            json_data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
        
    def get_info(self) -> Dict[str, Any]:
        """获取项目信息的副本
        
        Returns:
            项目信息字典
        """
        return self._info.copy()
        
    def get_version(self) -> str:
        """获取程序版本号
        
        Returns:
            版本号字符串
        """
        return self._info["version"]
        
    def get_app_name(self) -> str:
        """获取程序名称
        
        Returns:
            程序名称
        """
        return self._info["name"]
        
    def verify_integrity(self) -> bool:
        """验证程序信息是否被篡改
        
        Returns:
            如果信息未被篡改，返回True，否则返回False
        """
        current_signature = self._generate_signature(self._info)
        return hmac.compare_digest(current_signature, self._signature)
        
    def get_build_info(self) -> str:
        """获取构建信息
        
        Returns:
            构建信息字符串
        """
        return (
            f"{self._info['name']} v{self._info['version']}\n"
            f"Build: {self._info['build_date']}\n"
            f"{self._info['copyright']}"
        )
    
    def get_about_info(self) -> str:
        """获取关于信息
        
        Returns:
            关于信息字符串
        """
        return (
            f"{self._info['name']} v{self._info['version']}\n\n"
            f"{self._info['description']}\n\n"
            f"作者：{self._info['author']}\n"
            f"许可证：{self._info['license']}\n"
            f"官网：{self._info['website']}\n\n"
            f"{self._info['copyright']}"
        )
    
    def generate_license_file(self, output_path: str = "LICENSE.txt") -> bool:
        """生成许可证文件
        
        Args:
            output_path: 输出文件路径
            
        Returns:
            生成是否成功
        """
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(f"{self._info['name']} v{self._info['version']}\n\n")
                f.write(f"{self._info['copyright']}\n\n")
                
                # 添加许可证文本，这里只是一个示例
                if self._info['license'] == "GPL-3.0":
                    f.write("This program is free software: you can redistribute it and/or modify\n")
                    f.write("it under the terms of the GNU General Public License as published by\n")
                    f.write("the Free Software Foundation, either version 3 of the License, or\n")
                    f.write("(at your option) any later version.\n\n")
                    
                    f.write("This program is distributed in the hope that it will be useful,\n")
                    f.write("but WITHOUT ANY WARRANTY; without even the implied warranty of\n")
                    f.write("MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the\n")
                    f.write("GNU General Public License for more details.\n\n")
                    
                    f.write("You should have received a copy of the GNU General Public License\n")
                    f.write("along with this program.  If not, see <https://www.gnu.org/licenses/>.\n")
            return True
        except Exception as e:
            print(f"生成许可证文件失败: {e}")
            return False
    
    def detect_runtime_tampering(self) -> bool:
        """检测运行时篡改
        
        Returns:
            如果检测到篡改，返回True，否则返回False
        """
        # 检测代码签名是否一致
        if not self.verify_integrity():
            return True
            
        # 检查当前脚本的哈希值是否被修改
        try:
            script_path = os.path.abspath(sys.argv[0])
            if os.path.exists(script_path):
                # 这里可以添加更复杂的完整性检查逻辑
                # 例如与预期的哈希值比较
                pass
        except Exception:
            # 异常可能意味着有人在尝试绕过检查
            return True
            
        return False


# 创建全局实例，便于其他模块导入使用
project_info = ProjectInfo()


# 简单的测试代码
if __name__ == "__main__":
    # 打印项目信息
    info = project_info.get_info()
    print(f"项目名称: {info['name']}")
    print(f"版本号: {info['version']}")
    print(f"构建日期: {info['build_date']}")
    print(f"作者: {info['author']}")
    
    # 验证完整性
    if project_info.verify_integrity():
        print("信息完整性验证通过")
    else:
        print("警告：信息已被篡改！")
    
    # 打印构建信息
    print("\n构建信息:")
    print(project_info.get_build_info())
    
    # 打印关于信息
    print("\n关于信息:")
    print(project_info.get_about_info()) 
import requests
import time
import random


def get_steam_game_name(appid, max_retries=2):
    """获取Steam游戏名称
    
    Args:
        appid: 游戏AppID
        max_retries: 最大重试次数
        
    Returns:
        str: 游戏名称或错误信息
    """
    # 添加中文语言参数和国家代码
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}&l=zh&cc=cn"
    print(f"请求URL: {url}")
    
    retry_count = 0
    last_error = None
    
    while retry_count <= max_retries:
        try:
            # 添加User-Agent头，模拟浏览器行为 - 使用多种UA随机化请求
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
            
            # 第一次请求不打印重试信息
            if retry_count > 0:
                print(f"第 {retry_count} 次重试获取游戏 {appid} 的名称...")
            
            response = requests.get(url, headers=headers, timeout=15)  # 增加超时时间
            
            # 打印响应状态码
            print(f"响应状态码: {response.status_code}")
            
            # 检查HTTP状态码
            if response.status_code != 200:
                raise requests.exceptions.HTTPError(f"HTTP错误: {response.status_code}")
            
            # 确保响应内容不为空
            if not response.text or response.text.strip() == '':
                raise ValueError("API返回了空响应")
            
            data = response.json()
            game_data = data.get(str(appid), {})
            
            if not game_data:
                raise ValueError(f"API返回数据中没有AppID {appid} 的信息")
                
            if not game_data.get('success', False):
                error_msg = f"错误：未找到AppID {appid} 的游戏信息，或接口访问失败。"
                print(error_msg)
                return error_msg

            # 确保data字段存在
            if 'data' not in game_data:
                raise KeyError("API响应中缺少'data'字段")
                
            # 确保name字段存在    
            if 'name' not in game_data['data']:
                raise KeyError("API响应中缺少'name'字段")

            name = game_data['data']['name']
            print(f"成功获取游戏名称: {name}")
            return name

        except requests.exceptions.RequestException as e:
            last_error = f"网络请求失败：{str(e)}"
            print(last_error)
        except KeyError as e:
            last_error = f"解析JSON数据时出错，缺少键: {str(e)}，请检查API响应格式是否变更。"
            print(last_error)
        except ValueError as e:
            last_error = f"数据验证错误: {str(e)}"
            print(last_error)
        except Exception as e:
            last_error = f"未知错误：{str(e)}"
            print(last_error)
        
        # 如果不是最后一次重试，则等待一段时间后重试
        if retry_count < max_retries:
            # 使用指数退避策略，每次失败后等待时间增加
            wait_time = 2 + retry_count * 2 + random.uniform(0, 1)
            print(f"将在 {wait_time:.1f} 秒后重试...")
            time.sleep(wait_time)
        
        retry_count += 1
    
    # 如果所有重试都失败，返回最后的错误
    return last_error


# 使用示例
if __name__ == "__main__":
    # 测试多个游戏ID
    test_ids = [10, 100, 570, 730]
    for appid in test_ids:
        print(f"\n测试 AppID {appid}:")
        game_name = get_steam_game_name(appid)
        print(f"AppID {appid} 对应的游戏名称是：{game_name}")
        
    print("\n测试完成")
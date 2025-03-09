import requests


def get_steam_game_name(appid):
    url = f"https://store.steampowered.com/api/appdetails?appids={appid}"
    try:
        response = requests.get(url)
        response.raise_for_status()  # 检查HTTP错误

        data = response.json()
        game_data = data.get(str(appid), {})

        if not game_data.get('success', False):
            return f"错误：未找到AppID {appid} 的游戏信息，或接口访问失败。"

        return game_data['data']['name']

    except requests.exceptions.RequestException as e:
        return f"网络请求失败：{str(e)}"
    except KeyError:
        return "解析JSON数据时出错，请检查API响应格式是否变更。"
    except Exception as e:
        return f"未知错误：{str(e)}"

def fetch_game_name(self, app_id: str, force: bool = True):
        """获取游戏名称

        Args:
            app_id: 游戏AppID
            force: 是否强制更新名称，即使游戏已有名称
        """
        # 显示进度信息


        # 使用Steam API获取游戏名称
        import requests
        import threading
        import time

        def fetch_name_task():
            # 定义多个可能的API和网页源
            sources = [
                # Steam官方API
                {
                    "name": "Steam API",
                    "type": "api",
                    "url": f"https://store.steampowered.com/api/appdetails?appids={app_id}",
                    "timeout": 5,  # 5秒超时
                    "extract": lambda data: data.get(str(app_id), {}).get('data', {}).get('name', None)
                    if data.get(str(app_id), {}).get('success', False) else None
                },
                # SteamSpy API (备用)
                {
                    "name": "SteamSpy API",
                    "type": "api",
                    "url": f"https://steamspy.com/api.php?request=appdetails&appid={app_id}",
                    "timeout": 5,
                    "extract": lambda data: data.get('name', None)
                }
            ]

            # 尝试每个来源
            last_error = None

            for source in sources:
                try:
                    # 添加延迟，避免请求过快
                    time.sleep(0.5)

                    # 进行网络请求
                    response = requests.get(source['url'], timeout=source['timeout'])

                    # 检查HTTP错误
                    response.raise_for_status()

                    if source['type'] == 'api':
                        # 解析JSON数据
                        data = response.json()

                        # 提取游戏名称
                        game_name = source['extract'](data)

                        if game_name:

                            return game_name

                except requests.exceptions.RequestException as e:
                    # 记录错误，但继续尝试下一个来源
                    last_error = e
                    continue
                except Exception as e:
                    # 记录错误，但继续尝试下一个来源
                    last_error = e
                    continue

            # 如果所有来源都失败
            if last_error:
                error_msg = f"所有获取方式都失败，最后一个错误: {str(last_error)}"

            else:
                error_msg = f"无法获取游戏 {app_id} 的名称，请检查游戏ID是否正确或稍后再试"





# 使用示例
appid = 730  # CS:GO 的AppID
#game_name = get_steam_game_name(appid)
game_name= fetch_game_name("10",True)
print(f"AppID {appid} 对应的游戏名称是：{game_name}")
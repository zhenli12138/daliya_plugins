import time
import random
import aiohttp
import asyncio
from typing import (Dict, Any, Optional, List)
import os
import json

class RaceHorse:
    def __init__(self):
        super().__init__()
        self.horse_path = "./data/plugins/horse.menu.png"
        self.config = ConfigManager("./data/plugins/horse.jsonl")  # 初始化配置管理器
        # 初始化配置参数
        self.callList: Dict[str, Dict] = {}
        # 初始化货币数据库，数据存放文件名为 monetary_db.json
        self.database = JsonlDatabase("monetary_db.json")

    '''----------------------------需要更改底层调用API函数---------------------------------'''
    async def send_group_message(self,group_id: str, text: str):
        '''napcat示例'''
        async with aiohttp.ClientSession() as session:
            ws_url = "ws://localhost:3001/"
            async with session.ws_connect(ws_url) as ws:
                print("已连接 WebSocket 服务器:", ws_url)
                payload = {
                    "action": "send_group_msg",
                    "params": {
                        "group_id": group_id,
                        "message": [
                            {
                                "type": "text",
                                "data": {"text": text}
                            }
                        ]
                    }
                }
                await ws.send_json(payload)
                print("通过 WebSocket 发送消息：", payload)

    async def cmd_start_race(self,group_id):
        """开始赛马，实时更新赛况"""
        guild_data = await self.get_guild_data(group_id)
        if not guild_data["waitingPlay"]:
            result = "还没准备呢，请先输入指令：赛马"
            await self.send_group_message(group_id, result)
            return
        if guild_data["isPlay"]:
            result = "当前正在游玩赛马，请等待结束~"
            await self.send_group_message(group_id, result)
            return
        guild_data["waitingPlay"] = False
        guild_data["isPlay"] = True
        # 定义赛马事件消息列表
        eventMessage = [
            {"message": "往反方向跑了...", "type": "debuff", "min": 3, "max": 6},
            {"message": "使出洪荒之力！", "type": "buff", "min": 1, "max": 5},
            {"message": "跑错跑道了！", "type": "change"},
            {"message": "光翼展开", "type": "up", "value": 2, "time": 4},
            {"message": "被沙子迷住眼睛", "type": "down", "value": 2, "time": 4},
            {"message": "摆烂", "type": "stop"},
            {"message": "带偏队伍", "type": "allDown"},
            {"message": "被风吹跑了", "type": "debuff", "min": 3, "max": 6},
            {"message": "跃迁引擎启动", "type": "buff", "min": 6, "max": 13},
            {"message": "一个滑铲", "type": "change"},
            {"message": "限界解除~", "type": "up", "value": 3, "time": 4},
            {"message": "力乏了", "type": "down", "value": 2, "time": 4},
            {"message": "歇业", "type": "stop"},
            {"message": "策反队伍", "type": "allDown"}
        ]
        debuffEvents = [m for m in eventMessage if m["type"] == "debuff"]
        buffEvents    = [m for m in eventMessage if m["type"] == "buff"]
        changeEvents  = [m for m in eventMessage if m["type"] == "change"]
        upEvents      = [m for m in eventMessage if m["type"] == "up"]
        downEvents    = [m for m in eventMessage if m["type"] == "down"]
        stopEvents    = [m for m in eventMessage if m["type"] == "stop"]
        allDownEvents = [m for m in eventMessage if m["type"] == "allDown"]
        # 定义各种赛马事件处理函数
        async def debuff(target: int, track: List[int], event_msg: dict):
            value = await self.random_int(event_msg.get("min", 0), event_msg.get("max", 1))
            track[target] = max(track[target] - value, 0)
            result = f"{target+1}号🐴{event_msg['message']}\n后退{value}格"
            await self.send_group_message(group_id,result)

        async def buff(target: int, track: List[int], event_msg: dict):
            value = await self.random_int(event_msg.get("min", 0), event_msg.get("max", 1))
            track[target] = track[target] + value if track[target] + value < guild_data["termination"] else guild_data["termination"]
            result = f"{target+1}号🐴{event_msg['message']}\n前进{value}格"
            await self.send_group_message(group_id, result)

        async def change(target: int, track: List[int], event_msg: dict):
            # 随机选取一个不同于 target 的马匹交换位置
            changeRandom = target
            while changeRandom == target:
                changeRandom = await self.random_int(0, len(track))
            track[target], track[changeRandom] = track[changeRandom], track[target]
            result=f"{target+1}号🐴{event_msg['message']}\n与{changeRandom+1}号🐴交换跑道"
            await self.send_group_message(group_id, result)

        async def up(target: int, strandedState: List[dict], event_msg: dict):
            strandedState.append({"target": target, "type": event_msg["value"], "time": event_msg["time"]})
            result = f"{target+1}号🐴{event_msg['message']}\n{event_msg['time']} 回合速度 + {event_msg['value']}"
            await self.send_group_message(group_id, result)

        async def down(target: int, strandedState: List[dict], event_msg: dict):
            strandedState.append({"target": target, "type": -event_msg["value"], "time": event_msg["time"]})
            result = f"{target+1}号🐴{event_msg['message']}\n{event_msg['time']} 回合速度 - {event_msg['value']}"
            await self.send_group_message(group_id, result)

        async def stop(target: int, strandedState: List[dict], event_msg: dict):
            strandedState.append({"target": target, "type": -guild_data["speed"][target], "time": 1})
            result = f"{target+1}号🐴{event_msg['message']}\n在原地停止思考中..."
            await self.send_group_message(group_id, result)

        async def alldown(target: int, speed: List[int], event_msg: dict):
            guild_data["isBack"] = True
            result = f"{target+1}号🐴{event_msg['message']}\n全体向反移动一次"
            await self.send_group_message(group_id, result)

        async def clear_track_data():
            if guild_data["timer"]:
                guild_data["timer"].cancel()
            guild_data["track"] = [0, 0, 0, 0, 0, 0]
            guild_data["speed"] = [0, 0, 0, 0, 0, 0]
            guild_data["strandedState"].clear()
            guild_data["isPlay"] = False
            guild_data["participant"].clear()
            guild_data["waitingPlay"] = False

        async def get_random_speed():
            new_speeds = [await self.random_int(1, 3) for _ in guild_data["speed"]]
            self.modify_array(guild_data["speed"], new_speeds)

        async def get_stranded_state():
            guild_data["strandedState"][:] = [item for item in guild_data["strandedState"] if item["time"] != 0]
            for item in guild_data["strandedState"]:
                guild_data["speed"][item["target"]] = max(guild_data["speed"][item["target"]] + item["type"], 0)
                item["time"] -= 1

        async def get_current_position():
            new_track = [pos + sp for pos, sp in zip(guild_data["track"], guild_data["speed"])]
            self.modify_array(guild_data["track"], new_track)

        async def send_format_track():
            lines = []
            for pos in guild_data["track"]:
                pos = max(0, min(pos, guild_data["termination"]))
                temp = int(pos / guild_data["termination"] * 20)
                arr = []
                for i in range(21):
                    arr.append("🐎" if i == temp else "-")
                arr.append("🚩")
                lines.append("".join(arr[::-1]))
            msg = "当前实况：\n" + "\n".join(lines)
            print("消息发送中")
            await self.send_group_message(group_id, msg)


        async def send_win_info_message():
            win_index = [i for i, pos in enumerate(guild_data["track"]) if pos >= guild_data["termination"]]
            win_data = "、".join(str(i+1) for i in win_index)
            await settlement_bonus(guild_data["participant"], win_index)
            result="恭喜" + win_data + "号马获得了冠军，冠军奖励已发放，请发送【赛马余额】查看"
            await self.send_group_message(group_id, result)


        async def settlement_bonus(participants: Dict, win_index: List[int]):
            win_users = []
            for uid, info in participants.items():
                if info["select"] - 1 in win_index:
                    win_users.append((uid, info["pay"]))
            messages = []
            for uid, pay in win_users:
                bonus = pay * self.config.get("rate", 5)
                user_data = await self.database.get_user(uid)
                new_balance = (user_data.get("value", 0) + bonus) if user_data else bonus
                await self.database.update_user(uid, {"value": new_balance})
                messages.append(f"id:{uid} 得到了{bonus}{self.config.get('currency', '润币')}")
            if messages:
                result="\n".join(messages)
                await self.send_group_message(group_id, result)

        async def is_all_down():
            guild_data["speed"] = [-sp for sp in guild_data["speed"]]
            guild_data["isBack"] = False

        result = "马儿开始跑了!"
        await self.send_group_message(group_id, result)

        async def race_loop():
            try:
                while True:
                    print("循环进行中")
                    await send_format_track()
                    await get_random_speed()
                    # 以 1/2 概率触发随机事件
                    if await self.random_int(1, 3) == 2:
                        # 从事件函数中随机选取一个
                        event_fn = random.choice([debuff, buff, change, up, down, stop, alldown])
                        target = await self.random_int(0, 6)
                        if event_fn == debuff:
                            if debuffEvents:
                                chosen = random.choice(debuffEvents)
                                await debuff(target, guild_data["track"], chosen)
                        elif event_fn == buff:
                            if buffEvents:
                                chosen = random.choice(buffEvents)
                                await buff(target, guild_data["track"], chosen)
                        elif event_fn == change:
                            if changeEvents:
                                chosen = random.choice(changeEvents)
                                await change(target, guild_data["track"], chosen)
                        elif event_fn == up:
                            if upEvents:
                                chosen = random.choice(upEvents)
                                await up(target, guild_data["strandedState"], chosen)
                        elif event_fn == down:
                            if downEvents:
                                chosen = random.choice(downEvents)
                                await down(target, guild_data["strandedState"], chosen)
                        elif event_fn == stop:
                            if stopEvents:
                                chosen = random.choice(stopEvents)
                                await stop(target, guild_data["strandedState"], chosen,)
                        elif event_fn == alldown:
                            if allDownEvents:
                                chosen = random.choice(allDownEvents)
                                await alldown(target, guild_data["speed"], chosen)
                    await get_stranded_state()
                    if guild_data["isBack"]:
                        await is_all_down()
                    await get_current_position()
                    if any(pos >= guild_data["termination"] for pos in guild_data["track"]):
                        print("循环结束")
                        await send_format_track()
                        await send_win_info_message()
                        await clear_track_data()
                        break
                    await asyncio.sleep(5)
            except asyncio.CancelledError:
                print("意外结束")
                pass

        guild_data["timer"] = asyncio.create_task(race_loop())
        await guild_data["timer"]
    '''-------------------------需要适配框架部分函数-------------------------'''
    async def cmd_store(self)->str:
        """
        展示赛马商店中的所有道具信息
        输出：str
        """
        available = "\n\n".join([f"[道具名] {p['name']}\n[价格] {p['money']}\n\"{p['info']}\"" for p in self.propList])
        result = "以下是对道具的使用价格和描述:\n\n使用道具请发送指令：赛马道具 道具名 目标\n\n" + available
        return result

    async def cmd_help(self)->str:
        """
        赛马游戏菜单
        输出：菜单图片地址
        """
        if not os.path.exists(self.horse_path):
            await self.horse_menu(self.horse_path)
            print(f"文件 {self.horse_path} 不存在，已创建并初始化。")
        return self.horse_path

    async def cmd_race(self,group_id)->str:
        """
        准备一场赛马
        输入：group_id
        输出：str
        """
        guild_data = await self.get_guild_data(group_id)
        if guild_data["isPlay"]:
            result = "游戏已经在进行" if group_id != "10000" else "游戏已经在别的私聊会话中进行，请等待"
            return result
        else:
            guild_data["waitingPlay"] = True
            result = "赛🐎 要开始了，可在开始之前选择其中 1-6 号🐎，指令为: 押 <马匹号> <金额> 去选择对应的马匹吧~"
            return result

    async def cmd_balance(self,user_id)->str:
        """
        查看当前余额
        输入：user_id
        输出：str
        """
        user_data = await self.database.get_user(user_id)
        if not user_data:
            num = await self.random_int(20, 100)
            await self.database.update_user(user_id, {"value": num})
            result = f"您可能是首次使用押功能，已给予您初始金额: {num} {self.config.get('currency', '润币')}~"
            return result
        else:
            balance = user_data.get("value", 0)
            identity = self.check_identity(balance)["name"]
            result = f"您当前{self.config.get('currency', '润币')}为：{balance} 点数。属于 {identity} 级别\n"
            if balance <= 5:
                num = await self.random_int(5, 10)
                await self.database.update_user(user_id, {"value": balance + num})
                result += f"啊咧，似乎查看余额的时候发现只有{balance}个{self.config.get('currency', '润币')}了吗... \n真是杂鱼大叔呢~❤️ 这次就再给你 {num} {self.config.get('currency', '润币')}吧~"
            return result

    async def cmd_bet(self, group_id,user_id,goal: int, currency: int)->str:
        """
        下注命令：押 <马匹号> <金额>
        输入：group_id,user_id,goal: int, currency: int
        输出：str
        """
        guild_data = await self.get_guild_data(group_id)
        user_data = await self.database.get_user(user_id)
        horse = goal
        money = currency
        if not guild_data["waitingPlay"]:
            result = "游戏还没开始"
            return result
        if user_id in guild_data["participant"]:
            result = "您已选择对应马匹，不要重复选择哦~"
            return result
        if horse > 6 or horse <= 0:
            result = "您选的马匹号码有误"
            return result
        if money < 0 or money > self.config.get("betMax", 70):
            result = f"押的金额过大或者过小。目前限制在 {self.config.get('betMax', 70)} 以内"
            return result
        if not user_data or user_data.get("value", 0) < money:
            result = "选择马匹失败，可能原因：额度不够"
            return result
        else:
            new_balance = user_data.get("value", 0) - money
            await self.database.update_user(user_id, {"value": new_balance})
            guild_data["participant"][user_id] = {"pay": money, "select": horse}
            result = f"您已选择{horse}号马，你的id为：{user_id}，选择的额度为：{money}{self.config.get('currency', '润币')}"
            return result

    async def cmd_end_race(self,group_id)->str:
        """
        结束当前赛马，并根据进程退还部分押注
        输入：group_id
        输出：str
        """
        guild_data = await self.get_guild_data(group_id)
        result = ''
        if not guild_data["isPlay"] and not guild_data["waitingPlay"]:
            result = "还没开始呢"
            return result
        for uid, bet in guild_data["participant"].items():
            # 如果比赛已开始，则退还一半押注金额，否则全额退还
            refund = bet["pay"] if guild_data["waitingPlay"] else int(bet["pay"] / 2.5)
            user_data = await self.database.get_user(uid)
            new_balance = (user_data.get("value", 0) + refund) if user_data else refund
            await self.database.update_user(uid, {"value": new_balance})
        if guild_data["waitingPlay"]:
            result += "已退还押注金额"
        else:
            result += "由于游戏已经开始，仅退还一半押注金额"
        if guild_data["timer"]:
            guild_data["timer"].cancel()
        guild_data["track"] = [0, 0, 0, 0, 0, 0]
        guild_data["speed"] = [0, 0, 0, 0, 0, 0]
        guild_data["strandedState"].clear()
        guild_data["isPlay"] = False
        guild_data["participant"].clear()
        guild_data["waitingPlay"] = False
        result += "已结束"
        return result

    async def cmd_prop(self,group_id,user_id,item:str,goal:Optional[int]=None)->str:
        """使用赛马道具干扰或辅助赛事"""
        guild_data = await self.get_guild_data(group_id)
        result = ''
        if not guild_data["isPlay"]:
            result = "似乎还没开始赛马..."
            return result
        last_time = guild_data["propTime"].get(user_id, 0)
        now = int(time.time() * 1000)
        if now - last_time < 10000:
            result="您使用道具太频繁了，请等待一会"
            return result
        guild_data["propTime"][user_id] = now
        if not item:
            available = "\n".join([p["name"] for p in self.propList])
            result="似乎还没有选择道具，目前存在的道具有：\n" + available
            return result
        prop_name = item
        target = None
        try:
            target = goal
        except:
            pass
        info = next((p for p in self.propList if p["name"] == prop_name), None)
        if not info:
            available = "\n".join([p["name"] for p in self.propList])
            result="道具不存在。目前存在的道具有：\n" + available
            return result
        # 扣除道具费用
        user_data = await self.database.get_user(user_id)
        if not user_data or user_data.get("value", 0) < info["money"]:
            result="对目标使用道具失败，可能原因：额度不够"
            return result
        await self.database.update_user(user_id, {"value": user_data.get("value", 0) - info["money"]})
        # 判断是否成功（依据概率）
        if await self.random_int(0, 11) > info["prob"] * 10:
            result=f"您尝试使用了{info['name']}，似乎失败了..."
            return result
        # 若存在 trackFun 则随机使某匹马回到起点
        if "trackFun" in info:
            index = await self.random_int(0, len(guild_data["track"]))
            guild_data["track"][index] = 0
            result=f"您的{info['name']}选中了{index+1}号🐎;\n{info['msg']}"
            return result
        # 若存在 statusFun 则对指定目标生效
        if "statusFun" in info:
            if target and 1 <= target <= 6:
                if info["statusFun"] == "excited":
                    guild_data["strandedState"].append({"target": target-1, "type": 2, "time": 5})
                elif info["statusFun"] == "fried":
                    guild_data["strandedState"].append({"target": target-1, "type": 10, "time": 2})
                result=f"您对{target}号🐎使用了道具 {info['name']};\n{info['msg']}"
                return result
            else:
                result="您对空气使用了道具，似乎没有选中目标，请确认目标！\n格式为：\n\n赛马道具 道具名 目标下标"
                return result
        # 若为普通直接修改跑道
        if target and 1 <= target <= 6:
            guild_data["track"][target-1] += info["value"]
            result=f"你对{target}号马使用了{info['name']};\n{info['msg']}"
            return result
        return result


    '''------------------------内部函数---------------------------'''
    # 道具列表
    propList = [
        {
            "name": "香蕉皮",
            "money": 10,
            "value": -8,
            "prob": 0.3,
            "info": "使用香蕉皮，有30%概率使目标马匹后退5格",
            "msg": "它摔倒了"
        },
        {
            "name": "一堆香蕉皮",
            "money": 30,
            "value": -5,
            "prob": 0.8,
            "info": "使用大量香蕉皮，有80%概率使目标马匹后退5格",
            "msg": "它摔倒了"
        },
        {
            "name": "兴奋剂",
            "money": 50,
            "value": 2,
            "statusFun": "excited",  # 标识后续按兴奋剂处理
            "prob": 1,
            "info": "使用兴奋剂，5回合速度 + 2",
            "msg": "它极其兴奋，开始飞快奔跑！！5回合 速度 +2"
        },
        {
            "name": "华来士炸鸡",
            "money": 50,
            "value": 10,
            "statusFun": "fried",   # 标识后续按炸鸡处理
            "prob": 0.1,
            "info": "使用华来士炸鸡，10%概率 2回合速度 + 10",
            "msg": "吃了华来士，化身喷射战士\n...糟糕，要喷射了！2回合 速度 +10"
        },
        {
            "name": "闪电风暴",
            "money": 10,
            "value": 2,
            "trackFun": "lightning",  # 标识按闪电风暴处理
            "prob": 1,
            "info": "随机抽一匹马 回到起点",
            "msg": "倒霉的🐎被电回了老家"
        }
    ]
    async def random_int(self, min_val: int, max_val: int) -> int:
        """返回 [min_val, max_val) 内的随机整数"""
        return random.randrange(min_val, max_val)

    def modify_array(self, arr: List, new_arr: List):
        """将列表 arr 原地替换为 new_arr 内容"""
        arr.clear()
        arr.extend(new_arr)

    def check_identity(self, sum_val: int) -> Dict:
        """根据金额返回用户级别"""
        types = [
            {"name": "懒惰的杂鱼", "num": 100},
            {"name": "努力的杂鱼", "num": 200},
            {"name": "勤劳的杂鱼", "num": 400},
            {"name": "梦想家", "num": 600},
            {"name": "赌徒", "num": 800},
            {"name": "富人", "num": 1000},
            {"name": "大佬", "num": 4000},
            {"name": "萌新", "num": 6000},
            {"name": "真萌新", "num": float('inf')}
        ]
        result = None
        for t in types:
            if sum_val <= t["num"]:
                result = t
                break
        return result

    async def get_guild_data(self, guild_id: Optional[str]) -> Dict:
        """获取某个群组（或私聊）的赛马数据"""
        info = guild_id if guild_id else "10000"
        if info not in self.callList:
            self.callList[info] = {
                "timer": None,         # 定时任务句柄
                "waitingPlay": False,  # 是否已进入等待下注状态
                "isPlay": False,       # 是否正在赛马中
                "propTime": {},        # 道具使用时间记录
                "termination": 30,     # 终点距离
                "track": [0, 0, 0, 0, 0, 0],  # 各马当前位置
                "speed": [0, 0, 0, 0, 0, 0],  # 各马当前速度
                "strandedState": [],   # 各马滞留状态（增益/减益）
                "isBack": False,       # 是否出现全体倒退
                "participant": {}      # 下注玩家记录，键为用户 id
            }
        return self.callList[info]

    async def horse_menu(self,path) -> str:
        """
        渲染排行榜并返回图片的 URL。
        使用外部 API 将 HTML 模板渲染为图片。
        """
        # 定义 HTML 模板
        TMPL = '''
        <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            body {
                background: linear-gradient(135deg, #f5f5dc 0%, #d2b48c 100%);
                font-family: 'Arial', sans-serif;
                padding: 20px;
            }

            .container {
                max-width: 800px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.9);
                border-radius: 15px;
                padding: 30px;
                box-shadow: 0 8px 20px rgba(0,0,0,0.15);
            }

            .title {
                text-align: center;
                color: #8b4513;
                font-size: 28px;
                margin-bottom: 25px;
                text-shadow: 2px 2px 3px rgba(0,0,0,0.1);
            }

            .menu-section {
                margin-bottom: 25px;
                padding: 20px;
                background: #fff7e6;
                border-radius: 10px;
                border-left: 5px solid #deb887;
                transition: transform 0.2s;
            }

            .menu-section:hover {
                transform: translateX(10px);
            }

            .section-title {
                color: #a0522d;
                font-size: 20px;
                margin-bottom: 15px;
                display: flex;
                align-items: center;
            }

            .section-title::before {
                content: "🐎";
                margin-right: 10px;
            }

            .command {
                color: #8b0000;
                font-weight: bold;
                background: #ffe4b5;
                padding: 2px 5px;
                border-radius: 3px;
            }

            .highlight {
                color: #cd853f;
                font-weight: bold;
            }

            .divider {
                height: 2px;
                background: linear-gradient(to right, transparent 0%, #deb887 50%, transparent 100%);
                margin: 25px 0;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1 class="title">🏇 赛马大会系统菜单 🏇</h1>

            <div class="menu-section">
                <div class="section-title">赛马余额</div>
                <p>🎯 新用户首次游玩请先发这个领钱！</p>
            </div>

            <div class="divider"></div>

            <div class="menu-section">
                <div class="section-title">创建比赛</div>
                <p>📝 创建一场赛马比赛，创建完成后进入下注环节</p>
            </div>

            <div class="menu-section">
                <div class="section-title">押注指令</div>
                <p>🎮 使用 <span class="command">押 &lt;马的序号&gt; &lt;押注金额&gt;</span></p>
                <p>💰 第一名奖励：<span class="highlight">5倍奖金</span></p>
                <p>📊 基础胜率：约 <span class="highlight">16%</span></p>
            </div>

            <div class="divider"></div>

            <div class="menu-section">
                <div class="section-title">开始比赛</div>
                <p>🏁 输入 <span class="command">开始赛马</span> 正式启动赛事</p>
            </div>

            <div class="menu-section">
                <div class="section-title">道具系统</div>
                <p>🎁 使用 <span class="command">赛马道具 &lt;道具名&gt; &lt;马的序号&gt;</span></p>
                <p>⚡ 在比赛进行中实时干扰赛事进程</p>
            </div>

            <div class="divider"></div>

            <div class="menu-section">
                <div class="section-title">赛马商店</div>
                <p>🛒 查看可用道具列表</p>
                <p>✨ 通过比赛获得的积分兑换特殊道具</p>
            </div>
        </div>
    </body>
    </html>
        '''
        render_data = {"key": 1}
        payload = {
            "tmpl": TMPL,
            "render_data": render_data,
            "width": 800,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                        "http://116.62.188.107:8000/render",
                        json=payload
                ) as response:

                    # 解析响应内容
                    try:
                        data = await response.json()
                    except Exception as e:
                        raw_response = await response.text()
                        print(f"无效的JSON响应！原始内容: {raw_response[:500]}")
                        raise

                    # 检查关键字段
                    if 'url' not in data:
                        if 'error' in data:
                            raise ValueError(f"服务器返回错误: {data['error']}")
                        elif 'message' in data:
                            raise ValueError(f"API错误: {data['message']}")
                        else:
                            raise KeyError("响应中缺少'url'字段，且无错误信息")

                    await self.download_images(data['url'], path)
                    return data['url']

        except aiohttp.ClientError as e:
            print(f"网络连接错误: {str(e)}")
            return "error: 无法连接渲染服务器"
        except Exception as e:
            print(f"未知错误: {str(e)}")
            return f"error: {str(e)}"

    async def download_images(self,url: str, save_path: str):
        """
        异步下载单个图片
        :param url: 图片URL地址
        :param save_path: 本地保存路径（包含文件名）
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        # 确保目录存在
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        # 写入文件
                        with open(save_path, 'wb') as f:
                            while True:
                                chunk = await response.content.read(1024)
                                if not chunk:
                                    break
                                f.write(chunk)
                        print(f"下载成功: {url} -> {save_path}")
                    else:
                        print(f"下载失败: {url} - HTTP状态码 {response.status}")
        except Exception as e:
            print(f"下载出错: {url} - {str(e)}")
'''---------------------数据库---------------------------'''
class JsonlDatabase:
    def __init__(self, file_path: str):
        self.file_path = file_path
        self._initialize_file()

    def _initialize_file(self):
        """确保数据文件存在"""
        if not os.path.exists(self.file_path):
            open(self.file_path, "a").close()

    async def _load_all(self) -> List[Dict]:
        """加载全部数据"""
        with open(self.file_path, "r") as f:
            return [json.loads(line) for line in f if line.strip()]

    async def _save_all(self, records: List[Dict]):
        """保存全部数据"""
        with open(self.file_path, "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    async def get_user(self, user_id: str) -> Optional[Dict]:
        """获取完整用户记录"""
        records = await self._load_all()
        for record in records:
            if record.get("userid") == user_id:
                return record
        return None

    async def update_user(self, user_id: str, update_data: Dict):
        """更新用户记录（合并更新）"""
        records = await self._load_all()
        updated = False
        for record in records:
            if record.get("userid") == user_id:
                record.update(update_data)
                updated = True
                break
        if not updated:  # 新用户
            new_record = {"userid": user_id, **update_data}
            records.append(new_record)
        await self._save_all(records)

'''---------------------插件配置---------------------------'''
class ConfigManager:
    def __init__(self, config_file: str):
        self.config_file = config_file
        self.default_config = {
            "rate": 5,                       # 猜中冠军马匹的奖励倍率
            "betMax": 70,                    # 最高下注上限
            "currency": "马币",              # 积分货币名称
            "debug": False,                  # 是否开启调试模式
        }
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_file):
            return self.default_config
        with open(self.config_file, "r") as f:
            for line in f:
                return {**self.default_config, **json.loads(line.strip())}
        return self.default_config

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)

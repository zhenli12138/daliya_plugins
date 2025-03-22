import json
import datetime
import os
from typing import List, Dict, Optional,Any
import aiohttp
import calendar
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime as Pdatetime, datetime
# 在插件中使用 ConfigManager
class Deer:
    def __init__(self):
        super().__init__()
        self.t2i_url = "http://116.62.188.107:8000/render"
        # 初始化配置管理器
        self.config = ConfigManager("./data/plugins/config.jsonl")
        # 初始化数据库和货币管理器
        self.database = JsonlDatabase("./data/plugins/deerpipe.jsonl")
        # 初始化配置参数
        self.currency = self.config.get("currency", "鹿币")
        self.max_help_times = self.config.get("maximum_helpsignin_times_per_day", 5)
        self.reset_cycle = self.config.get("Reset_Cycle", "每月")
        self.cost_table = self.config.get("cost", {})

    '''-------------------------需要适配框架部分函数-------------------------'''
    async def view_calendar(self,user_id,user_name,target_user_id:Optional[str]=None,target_user_name:Optional[str]=None):
        '''
        查看用户签到日历
        输入：user_id,user_name,target_user_id（可选），target_user_name（可选）
        输出：日历图片地址/None
        '''
        if target_user_id and target_user_name:
            user_id = target_user_id
            user_name = target_user_name
        #时间模块
        current_date = datetime.datetime.now()
        year = current_date.year
        month = current_date.month
        #
        record = await self.get_user_record(user_id)
        if not record:
            msg = "未找到该用户的签到记录。"
            return None
        #
        calendar_image = await self.render_sign_in_calendar(record, year, month, user_name)
        return calendar_image

    async def deer_sign_in(self,user_id,user_name):
        '''
        用户签到
        输入：user_id,user_name
        输出：str + 日历图片地址/None
        '''
        current_date = datetime.datetime.now()
        year = current_date.year
        month = current_date.month
        day = current_date.day
        calendar_image = None
        #
        record = await self.get_user_record(user_id)
        if not record:
            record = await self.create_user_record(user_id, user_name)
        #
        if self.reset_cycle == "每月" and record["recordtime"] != f"{year}-{month}":
            await self.reset_user_record(user_id,f"{year}-{month}")
        #
        times = await self.get_sign_in_record(user_id, day)
        if times >= 3:
            msg = "今天已经鹿过3次了，给牛牛放个假，请明天再鹿吧~"
            return msg,calendar_image
        #
        await self.update_sign_in_record(user_id, day)
        reward = self.cost_table["checkin_reward"]["鹿"]["cost"]
        await self.modify_currency(user_id, reward)
        #
        times = await self.get_sign_in_record(user_id, day)
        currency = await self.get_currency(user_id)
        msg = f"你今天已经鹿了 {times} 次啦~ 继续加油咪~\n本次签到获得 {self.cost_table['checkin_reward']['鹿']['cost']} 个 {self.currency}。\n当前您总共拥有 {currency} 个 {self.currency}"
        calendar_image = await self.view_calendar(user_id,user_name)
        return msg,calendar_image

    async def resign(self,user_id,user_name,day: int):
        '''
        用户补签某日
        输入：user_id,user_name,day:int
        输出：str + 日历图片地址/None
        '''
        current_date = datetime.datetime.now()
        record = await self.get_user_record(user_id)
        calendar_image = None
        if not record:
            msg = "暂无鹿管记录哦，快去【鹿】吧~"
            return msg,calendar_image
        if day < 1 or day > 31 or day > current_date.day:
            msg = "日期不正确或未到，请输入有效的日期。\n示例：【补鹿 1】"
            return msg,calendar_image
        #
        times = await self.get_sign_in_record(user_id, day)
        if times >= 3:
            msg = "指定日期已经鹿过3次了，不能再补鹿了！"
            return msg,calendar_image
        #
        await self.update_sign_in_record(user_id, day)
        reward = self.cost_table["checkin_reward"]["补鹿"]["cost"]
        await self.modify_currency(user_id, reward)
        currency = await self.get_currency(user_id)
        #
        msg = f"你已成功补签{day}号。{self.currency} 变化：{self.cost_table['checkin_reward']['补鹿']['cost']}。\n当前您总共拥有 {currency} 个 {self.currency}"
        calendar_image = await self.view_calendar(user_id,user_name)
        return msg,calendar_image

    async def cancel_sign_in(self,user_id,user_name,day: Optional[int] = None):
        '''
        用户取消某日签到
        输入：user_id,user_name,day:int(若无则为当日）
        输出：str + 日历图片地址/None
        '''
        current_date = datetime.datetime.now()
        day = day if day else current_date.day
        record = await self.get_user_record(user_id)
        calendar_image = None
        if not record:
            msg = "你没有签到记录。"
            return msg,calendar_image

        if day < 1 or day > 31 or day > current_date.day:
            msg = "日期不正确，请输入有效的日期。\n示例：【戒鹿 1】"
            return msg,calendar_image

        times = await self.get_sign_in_record(user_id, day)
        if times <= 0:
            msg = f"你没有在{day}号签到。"
            return msg,calendar_image

        await self.cancel_sign_in_on_day(user_id, day)
        reward = self.cost_table["checkin_reward"]["戒鹿"]["cost"]
        await self.modify_currency(user_id, reward)

        msg = f"你已成功取消{day}号的签到。点数变化：{self.cost_table['checkin_reward']['戒鹿']['cost']}"
        calendar_image = await self.view_calendar(user_id,user_name)
        return msg,calendar_image

    async def help_sign_in(self,user_id,user_name,target_user_id,target_user_name):
        '''
        用户帮助某人签到
        输入：user_id,user_name,target_user_id,target_user_name
        输出：str + 日历图片地址/None
        '''
        calendar_image = None
        if not target_user_id and not target_user_name:
            msg = "请指定要帮鹿管的用户【帮鹿@xx】"
            return msg,calendar_image
        #
        current_date = datetime.datetime.now()
        year = current_date.year
        month = current_date.month
        day = current_date.day
        # 数据获取
        record = await self.get_user_record(target_user_id)
        if not record:
            record = await self.create_user_record(target_user_id, target_user_name)
        # 重置方法
        if self.reset_cycle == "每月" and record["recordtime"] != f"{year}-{month}":
            await self.reset_user_record(target_user_id,f"{year}-{month}")
            record = await self.get_user_record(target_user_id)
        # 道具效果
        if not record["allowHelp"]:
            msg = "TA的牛牛带了锁，你帮不了TA鹿管了"
            return msg,calendar_image
        # 限制
        times = await self.get_sign_in_record(target_user_id, day)
        if times >= 3:
            msg = "TA今天已经鹿过3次了，给好兄弟的牛牛放个假，明天再帮TA鹿吧~"
            return msg,calendar_image
        # 限制
        if await self.is_help_sign_in_limit_reached(user_id, day):
            msg = "你今天已经帮助别人签到达到上限，无法继续帮助~"
            return msg,calendar_image

        # 执行帮助操作
        await self.update_sign_in_record(target_user_id, day)
        # 钱币计算
        reward = self.cost_table["checkin_reward"]["鹿"]["cost"]
        await self.modify_currency(target_user_id, reward)
        reward = self.cost_table["checkin_reward"]["鹿@用户"]["cost"]
        await self.modify_currency(user_id, reward)
        currency = await self.get_currency(user_id)
        # 消息构建
        times = await self.get_sign_in_record(target_user_id, day)
        msg = f"你成功帮助 {target_user_name} 鹿管！他今天已经鹿了 {times} 次了！您获得 {self.cost_table['checkin_reward']['鹿@用户']['cost']} 个 {self.currency}。\n当前您总共拥有 {currency} 个 {self.currency}"
        calendar_image = await self.view_calendar(user_id,user_name,target_user_id,target_user_name)
        return msg,calendar_image

    async def leaderboard(self):
        '''
        查看签到排行榜
        输入：无
        输出：日历图片地址/None
        '''
        current_month = datetime.datetime.now().month
        top_records = await self.get_leader_records()
        leaderboard_image = await self.render_leaderboard(top_records, current_month)
        return leaderboard_image

    async def toggle_lock(self, user_id):
        '''
        用户允许/禁止别人帮你鹿
        输入：user_id
        输出：str
        '''
        record = await self.get_user_record(user_id)
        if not record:
            msg = "用户未找到，请先进行签到。"
            return msg

        if "锁" not in record["itemInventory"]:
            msg = "你没有道具【锁】，无法执行此操作。\n请使用指令：购买 锁"
            return msg

        record["allowHelp"] = not record["allowHelp"]
        record["itemInventory"].remove("锁")
        await self.database.update_user(user_id, record)

        status = "允许" if record["allowHelp"] else "禁止"
        msg = f"你已经{status}别人帮助你鹿管。"
        return msg

    async def use_item(self,item_name: str,user_id,user_name,target_user_id:Optional[str]=None,target_user_name:Optional[str]=None):
        '''
        用户使用道具
        输入：item_nam,user_id,user_name,target_user_id（可选）,target_user_name（可选）
        输出：str + image/None
        '''
        image = None
        record = await self.get_user_record(user_id)
        if not record:
            record = await self.create_user_record(user_id, user_name)
        # 检查用户是否拥有该道具
        if "itemInventory" not in record or item_name not in record["itemInventory"]:
            msg = f"你没有道具：{item_name}。"
            return msg,image
        # 执行道具效果
        if item_name == "钥匙":
            # 使用钥匙强制帮助签到
            if not target_user_id and not target_user_name:
                msg = "请指定要强制帮鹿管的用户【使用 钥匙@xx】"
                return msg,image
            # 调用帮助签到逻辑
            # 移除道具
            record2 = await self.get_user_record(target_user_id)
            if not record2:
                msg = "用户未找到"
                return msg,image
            record2["allowHelp"] = not record2["allowHelp"]
            await self.database.update_user(target_user_id, record2)

            record["itemInventory"].remove(item_name)
            await self.database.update_user(user_id, record)
            msg = f"你使用了【钥匙】强制帮 {target_user_id} 鹿管。\n"
            result,image = await self.help_sign_in(user_id,user_name,target_user_id,target_user_name)
            msg = msg + result
            return msg,image
        else:
            msg = f"道具 {item_name} 暂无使用效果。"
            return msg,image

    async def buy_item(self,item_name: str,user_id,user_name):
        '''
        用户购买道具
        输入：item_nam,user_id,user_name
        输出：str
        '''
        #
        record = await self.get_user_record(user_id)
        if not record:
            record = await self.create_user_record(user_id, user_name)

        # 查找商品
        item_info = next(
            (item for item in self.cost_table["store_item"] if item["item"] == item_name),
            None
        )

        if not item_info:
            msg = "没有这个商品哦~"
            return msg

        cost = abs(item_info["cost"])
        if record["value"] < cost:
            msg = f"余额不足，需要 {cost} {self.currency}"
            return msg

        # 扣款并添加道具
        await self.modify_currency(user_id, -cost)
        new_items = record["itemInventory"] + [item_name]
        await self.database.update_user(user_id, {"itemInventory": new_items})
        msg = f"成功购买 {item_name}！"+f"当前余额：{record['value'] - cost} {self.currency}"
        return msg

    '''------------------------内部函数---------------------------'''
    async def create_user_record(self, user_id: str, user_name: str) -> Dict:
        """获取或创建用户记录（包含货币字段）"""
        user = await self.database.get_user(user_id)
        if not user:
            default_record = {
                "username": user_name,
                "recordtime": datetime.datetime.now().strftime("%Y-%m"),
                "checkindate": [],
                "helpsignintimes": "",
                "totaltimes": 0,
                "allowHelp": True,
                "itemInventory": [],
                "value": 0
            }
            await self.database.update_user(user_id, default_record)
            return default_record
        return user
    async def get_user_record(self, user_id: str) -> Dict:
        '''获取用户记录'''
        record = await self.database.get_user(user_id)
        return record if record else None
    async def modify_currency(self, user_id: str, amount: int):
        """修改用户余额"""
        user = await self.database.get_user(user_id)
        if user:
            new_value = user.get("value", 0) + amount
            await self.database.update_user(user_id, {"value": new_value})
    async def get_currency(self, user_id: str) -> int:
        """获取用户余额"""
        user = await self.database.get_user(user_id)
        return user.get("value", 0) if user else 0
    async def get_sign_in_record(self, user_id, day: int):
        '''检查签到次数是否达到上限'''
        record = await self.database.get_user(user_id)
        day_record = next((d for d in record["checkindate"] if d.startswith(f"{day}=")), None)
        if day_record:
            count = int(day_record.split("=")[1])
            return count
        else:
            return 0
    async def update_sign_in_record(self, user_id, day: int):
        '''更新签到记录'''
        record = await self.get_user_record(user_id)
        day_record = next((d for d in record["checkindate"] if d.startswith(f"{day}=")), None)
        # 更新签到数据
        new_checkindate = record["checkindate"].copy()
        if day_record:
            count = int(day_record.split("=")[1]) + 1
            new_checkindate.remove(day_record)
            new_checkindate.append(f"{day}={count}")
        else:
            new_checkindate.append(f"{day}=1")
        # 只更新必要字段
        await self.database.update_user(user_id, {
            "checkindate": new_checkindate,
            "totaltimes": record["totaltimes"] + 1
        })
    async def cancel_sign_in_on_day(self,user_id, day: int):
        '''取消某日签到'''
        record = await self.get_user_record(user_id)
        day_record = next((d for d in record["checkindate"] if d.startswith(f"{day}=")), None)
        if day_record:
            new_checkindate = [d for d in record["checkindate"] if d != day_record]
            await self.database.update_user(user_id, {
                "checkindate": new_checkindate,
                "totaltimes": record["totaltimes"] - 1
            })
    async def is_help_sign_in_limit_reached(self, user_id: str, day: int) -> bool:
        '''帮助次数限制检测'''
        record = await self.get_user_record(user_id)
        if not record:
            return False
        helpsignintimes = record.get("helpsignintimes", "")
        if helpsignintimes:
            helpsignintimes_dict = dict(entry.split("=") for entry in helpsignintimes.split(",") if "=" in entry)
            day_count = int(helpsignintimes_dict.get(str(day), 0))
            return day_count >= self.max_help_times
        return False
    async def reset_user_record(self, user_id: str,recordtime: str):
        '''重置用户记录（保留货币和道具）'''
        await self.database.update_user(user_id, {
            "recordtime": recordtime,
            "checkindate": [],
            "helpsignintimes": "",
            "totaltimes": 0,
            # 注意：不重置以下字段
            # "value": 保留原有余额
            # "itemInventory": 保留道具
            # "allowHelp": 保留原有设置
        })
    async def get_leader_records(self) -> List[Dict]:
        records = []
        try:
            with open("./data/plugins/deerpipe.jsonl", "r") as f:
                for line in f:
                    record = json.loads(line.strip())
                    records.append(record)
            current_month = datetime.datetime.now().month
            current_year = datetime.datetime.now().year
            valid_records = [record for record in records if
                             record["recordtime"] == f"{current_year}-{current_month}" and record["totaltimes"] > 0]
            valid_records.sort(key=lambda x: x["totaltimes"], reverse=True)
            return valid_records
        except FileNotFoundError:
            # 如果文件不存在，返回空列表
            return []

    async def render_leaderboard(self,records: List[Dict], month: int) -> str:
        """
        渲染排行榜并返回图片的 URL。
        使用外部 API 将 HTML 模板渲染为图片。
        """
        # 定义 HTML 模板
        TMPL = '''
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>鹿管排行榜</title>
        <style>
        body {
        font-family: 'Microsoft YaHei', Arial, sans-serif;
        background-color: #f0f4f8;
        margin: 0;
        padding: 20px;
        display: flex;
        justify-content: center;
        align-items: flex-start;
        }
        .container {
        background-color: white;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        padding: 30px;
        width: 100%;
        width: 500px;
        }
        h1 {
        text-align: center;
        color: #2c3e50;
        margin-bottom: 30px;
        font-size: 28px;
        }
        .ranking-list {
        list-style-type: none;
        padding: 0;
        margin: 0;
        }
        .ranking-item {
        display: flex;
        align-items: center;
        padding: 15px 10px;
        border-bottom: 1px solid #ecf0f1;
        transition: background-color 0.3s;
        }
        .ranking-item:hover {
        background-color: #f8f9fa;
        }
        .ranking-number {
        font-size: 18px;
        font-weight: bold;
        margin-right: 15px;
        min-width: 30px;
        color: #7f8c8d;
        }
        .medal {
        font-size: 24px;
        margin-right: 15px;
        }
        .name {
        flex-grow: 1;
        font-size: 18px;
        }
        .channels {
        font-size: 14px;
        color: #7f8c8d;
        margin-left: 10px;
        }
        .count {
        font-weight: bold;
        color: #e74c3c;
        font-size: 18px;
        }
        .count::after {
        content: ' 次';
        font-size: 14px;
        color: #95a5a6;
        }
        </style>
        </head>
        <body>
        <div class="container">
        <h1>🦌 {{ month }}月鹿管排行榜 🦌</h1>
        <ol class="ranking-list">
        {% for record in records %}
        <li class="ranking-item">
        <span class="ranking-number">{{ loop.index }}</span>
        {% if loop.index == 1 %}<span class="medal">🥇</span>{% endif %}
        {% if loop.index == 2 %}<span class="medal">🥈</span>{% endif %}
        {% if loop.index == 3 %}<span class="medal">🥉</span>{% endif %}
        <span class="name">{{ record.username }}</span>
        <span class="count">{{ record.totaltimes }}</span>
        </li>
        {% endfor %}
        </ol>
        </div>
        </body>
        </html>
        '''
        render_data = {
            "month": month,
            "records": records,
        }
        payload = {
            "tmpl": TMPL,
            "render_data": render_data,
            "width": 500,
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.t2i_url,json=payload) as response:
                return (await response.json())["url"]

    async def render_sign_in_calendar(self,record: Dict, year: int, month: int, user_name: str) -> str:
        """
        渲染签到日历为图片，并返回图片的 Base64 编码
        参数:
            record (Dict): 用户签到记录
            year (int): 年份
            month (int): 月份
            user_name (str): 用户名
        """
        day_bg_path = "./data/plugins/astrbot_plugin_comp_entertainment/day.png"
        check_mark_path = "./data/plugins/astrbot_plugin_comp_entertainment/check.png"
        save_path = "./data/plugins/astrbot_plugin_comp_entertainment/calendar.png"
        font = ImageFont.truetype("./data/plugins/astrbot_plugin_comp_entertainment/MiSans-Regular.ttf", 16)
        # 获取签到记录
        checkindate = record.get("checkindate", [])
        checkin_days = set()
        for entry in checkindate:
            if "=" in entry:
                day, _ = entry.split("=")
                checkin_days.add(int(day))
            else:
                checkin_days.add(int(entry))

        # 生成日历
        cal = calendar.monthcalendar(year, month)
        month_name = calendar.month_name[month]
        month_name = Pdatetime.strptime(month_name, '%B').month
        # 创建图片
        cell_size = 50
        padding = 20
        width = cell_size * 7 + padding * 2
        height = cell_size * (len(cal) + 1) + padding * 3
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        # 绘制标题
        title = f"{year}-{month_name}  鹿了\n{user_name}"
        bbox = draw.textbbox((0, 0), title, font=font)  # 获取文本的边界框
        title_width = bbox[2] - bbox[0]  # 计算文本宽度
        title_height = bbox[3] - bbox[1]  # 计算文本高度
        draw.text((10, padding), title, fill="black", font=font)

        # 绘制星期标题
        weekdays = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(weekdays):
            x = padding + i * cell_size
            y = padding + title_height + 10
            draw.text((x, y), day, fill="black", font=font)

        if not os.path.exists(day_bg_path) or not os.path.exists(check_mark_path):
            raise FileNotFoundError("背景图片或签到标记图片未找到。")

        day_bg = Image.open(day_bg_path).resize((cell_size, cell_size))
        check_mark = Image.open(check_mark_path).resize((cell_size, cell_size))

        # 绘制日历
        for week_idx, week in enumerate(cal):
            for day_idx, day in enumerate(week):
                if day == 0:
                    continue  # 跳过空白日期
                x = padding + day_idx * cell_size
                y = padding + title_height + 40 + week_idx * cell_size

                # 绘制背景图片
                image.paste(day_bg, (x, y))

                # 绘制日期
                draw.text((x + 10, y + 10), str(day), fill="black", font=font)

                # 标记已签到日期
                if day in checkin_days:
                    image.paste(check_mark, (x, y), check_mark)

        image.save(save_path, format="PNG")
        return save_path
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
            "currency": "鹿币",
            "maximum_helpsignin_times_per_day": 5,
            "enable_deerpipe": True,
            "Reset_Cycle": "每月",
            "cost": {
                "checkin_reward": {
                    "鹿": {"cost": 100},
                    "鹿@用户": {"cost": 100},
                    "补鹿": {"cost": -100},
                    "戒鹿": {"cost": -100},
                },
                "store_item": [
                    {"item": "锁", "cost": -50},
                    {"item": "钥匙", "cost": -250},
                ],
            },
        }
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not os.path.exists(self.config_file):
            return self.default_config

        with open(self.config_file, "r") as f:
            for line in f:
                return {**self.default_config, ** json.loads(line.strip())}
        return self.default_config

    def get(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


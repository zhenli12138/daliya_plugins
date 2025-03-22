import random
from random import random
from astrbot.api.all import *
from PIL import Image, ImageDraw, ImageFont, ImageOps
import json
from collections import defaultdict
from pathlib import Path
op = 0

class DdzGame:
    def __init__(self):
        self.ddzpath = Path('./data/plugins/data.jsonl') #根据实际情况更改
        self.rooms = {}
        self.player_rooms = {}
        if not os.path.exists(self.ddzpath):
            self.save_game()
            print(f"文件 {self.ddzpath} 不存在，已创建并初始化。")
        else:
            print(f"文件 {self.ddzpath} 已存在，跳过创建。")
        self.load_game()

    '''----------------------------需要更改底层调用API函数---------------------------------'''
    async def look_card(self,user_id)->None:
        room_id = self.player_rooms.get(user_id)
        if not room_id:
            msg = f"您还没有加入任何游戏房间"
            return
        players = self.rooms[room_id]['players']
        if user_id in players:
            idx = players.index(user_id)
            hand_img = await self.generate_hand_image(self.rooms[room_id]['game']['hands'][user_id], idx)
            msg = f"您的手牌为："
            return

    '''----------------------------需要适配框架部分函数---------------------------------'''
    async def exit_game(self, room_id)->str:
        '''
        结束游戏
        输入：room_id
        输出：str
        '''
        players = self.rooms[room_id]['players']
        self.rooms.pop(room_id, None)
        for p in players:
            self.player_rooms.pop(p, None)
        self.save_game()
        msg = "已解散房间，游戏结束！"
        return msg

    async def exit_room(self, room_id, user_id)->str:
        '''
        退出房间
        输入：room_id，user_id
        输出：str
        '''
        players = self.rooms[room_id]['players']
        is_host = players[0] == user_id
        if room_id not in self.rooms:
            msg = "该群没有游戏房间！"
            return msg
        if user_id not in players:
            msg = "你没在游戏房间！"
            return msg
        # 处理不同退出场景
        if is_host:
            exit_type = "房主"  # 此处 is_host 为 True，则 exit_type 固定为 "房主"
            for p in players:
                self.player_rooms.pop(p, None)
            self.rooms.pop(room_id, None)
            msg = f"{exit_type}已解散房间，游戏结束！"
            return msg
        else:
            # 普通玩家退出
            if self.rooms[room_id]['state'] == "playing":
                msg = "游戏进行中无法退出！"
                return msg
            # 从房间移除玩家
            self.rooms[room_id]['players'].remove(user_id)
            self.player_rooms.pop(user_id, None)
            if user_id in self.rooms[room_id]['game']['hands']:
                self.rooms[room_id]['game']['hands'].pop(user_id)
            msg = f"玩家 {user_id} 已退出房间。\n当前人数：{len(self.rooms[room_id]['players'])}"
            if not self.rooms[room_id]['players']:
                self.rooms.pop(room_id, None)
                msg = msg + "\n已解散房间，游戏结束！"
            return msg

    async def create_room(self, room_id, user_id)->str:
        '''
        创建房间
        输入：room_id，user_id
        输出：str
        '''
        if user_id in self.player_rooms:
            msg = "您已经在房间中！"
            return msg
        if room_id in self.rooms:
            msg = f"房间 {room_id} 已存在！"
            return msg
        self.player_rooms[user_id] = room_id
        self.rooms[room_id] = {
            'players': [user_id],
            'game': {
                'current_player': '',
                'dipai': [],
                'deck': [],
                'hands': {},
                'bid_count': '',
                'dizhu': '',
                'current_robber': '',
                'current_bidder': '',
                'last_played': {}
            },
            'state': 'waiting'
        }
        msg = f"房间创建成功！房间号：{room_id}\n等待其他玩家加入..."
        return msg

    async def join_room(self, room_id, user_id)->str:
        '''
        加入房间
        输入：room_id，user_id
        输出：str
        '''
        if room_id not in self.rooms:
            msg = f"房间 {room_id} 不存在！"
            return msg
        if user_id in self.rooms[room_id]['players']:
            msg = f"你已经加入房间 {room_id}！"
            return msg
        if len(self.rooms[room_id]['players']) == 3:
            msg = f"房间 {room_id} 人数已满！"
            return msg
        self.rooms[room_id]['players'].append(user_id)
        self.player_rooms[user_id] = room_id
        msg = f"成功加入房间 {room_id}！当前人数：{len(self.rooms[room_id]['players'])}"
        return msg

    async def start_game(self, room_id)->str:
        '''
        开始游戏
        输入：room_id
        输出：str
        '''
        if len(self.rooms[room_id]['players']) == 3:
            players = self.rooms[room_id]['players']
            self.rooms[room_id]['state'] = "发牌阶段"
            self.rooms[room_id]['game']['deck'] = self.generate_deck()
            deck = self.rooms[room_id]['game']['deck']
            random.shuffle(deck)
            self.rooms[room_id]['game']['hands'] = {
                p: sorted(deck[i * 17:(i + 1) * 17], key=lambda x: self.card_value(x))
                for i, p in enumerate(players)
            }
            self.rooms[room_id]['game']['dipai'] = deck[51:54]
            msg = "发牌结束，请在私聊中看牌！"
            # 为每个玩家调用看牌函数
            for player in self.rooms[room_id]['players']:
                await self.look_card(player)
            self.rooms[room_id]['state'] = "叫地主阶段"
            self.rooms[room_id]['game']['bid_count'] = '1'
            self.rooms[room_id]['game']['current_bidder'] = random.choice(players)
            msg += f"\n叫地主开始！当前叫牌玩家：{self.rooms[room_id]['game']['current_bidder']}"
            global op
            op = 0
            idx = players.index(self.rooms[room_id]['game']['current_bidder']) + op
            self.rooms[room_id]['game']['current_robber'] = players[(idx + 1) % 3]
            msg += f"\n抢地主阶段：请问你是否选择抢地主？当前抢地主玩家：{self.rooms[room_id]['game']['current_robber']}\n发送【/抢地主】抢地主，发送【/不抢】不抢。"
            return msg
        else:
            msg = f"房间 {room_id} 未满3人！当前人数：{len(self.rooms[room_id]['players'])}"
            return msg

    async def not_robber(self, room_id, user_id)->str:
        '''
        不抢地主
        输入 room_id, user_id
        输出 str
        '''
        if user_id == self.rooms[room_id]['game']['current_bidder']:
            msg = f"您已叫地主，当前地主玩家为 {self.rooms[room_id]['game']['current_bidder']}"
            return msg
        elif user_id == self.rooms[room_id]['game']['current_robber']:
            self.rooms[room_id]['game']['bid_count'] = str(int(self.rooms[room_id]['game']['bid_count']) + 1)
            global op
            op = 1
            msg = f"您选择不抢地主，当前地主玩家为 {self.rooms[room_id]['game']['current_bidder']}"
            bid_msg = await self.bid(room_id)
            return msg + "\n" + bid_msg
        else:
            msg = f"目前不是你的回合，用户 {user_id}"
            return msg

    async def robber(self, room_id, user_id)->str:
        '''
        抢地主
        输入 room_id, user_id
        输出 str
        '''
        if user_id == self.rooms[room_id]['game']['current_bidder']:
            msg = f"您已叫地主，当前地主玩家为 {self.rooms[room_id]['game']['current_bidder']}"
            return msg
        elif user_id == self.rooms[room_id]['game']['current_robber']:
            self.rooms[room_id]['game']['bid_count'] = str(int(self.rooms[room_id]['game']['bid_count']) + 1)
            self.rooms[room_id]['game']['current_bidder'] = self.rooms[room_id]['game']['current_robber']
            msg = f"您已抢地主，当前地主玩家为 {self.rooms[room_id]['game']['current_bidder']}"
            bid_msg = await self.bid(room_id)
            return msg + "\n" + bid_msg
        else:
            msg = f"目前不是你的回合，用户 {user_id}"
            return msg

    async def handle_play(self, room_id, user_id, cards_str: str)->str:
        '''
        出牌
        输入 room_id, user_id，cards_str
        输出 str
        '''
        players = self.rooms[room_id]['players']
        msg,flag = await self.check_game(room_id, user_id)
        msg = ''
        if not flag:
            return "校验失败，无法出牌。"

        parsed_cards = self.parse_cards(cards_str, self.rooms[room_id]['game']['hands'][user_id])
        if not parsed_cards:
            return "出牌无效！请检查牌型或是否拥有这些牌"

        play_type = self.validate_type(parsed_cards)
        if not play_type[0]:
            return "不合法的牌型！"

        if self.rooms[room_id]['game']['last_played']:
            if play_type[0] in ['rocket']:
                msg = "火箭发射！"
            elif play_type[0] in ['bomb']:
                if self.rooms[room_id]['game']['last_played']['type'][0] in ['rocket'] or not self.compare_plays(
                        self.rooms[room_id]['game']['last_played']['type'], play_type):
                    return "出牌不够大！"
            else:
                if len(parsed_cards) != len(self.rooms[room_id]['game']['last_played']['cards']):
                    return "出牌数量不一致！"
                if not self.compare_plays(self.rooms[room_id]['game']['last_played']['type'], play_type):
                    return "出牌不够大！"

        for c in parsed_cards:
            self.rooms[room_id]['game']['hands'][user_id].remove(c)
        self.rooms[room_id]['game']['last_played'] = {
            'player': user_id,
            'cards': parsed_cards,
            'type': play_type
        }
        msg += f"\n{user_id} 出牌：{' '.join(parsed_cards)}"
        await self.look_card(user_id)

        if not self.rooms[room_id]['game']['hands'][user_id]:
            if user_id == self.rooms[room_id]['game']['dizhu']:
                winners = [user_id]
                results = f"地主获胜！胜者：{winners}"
            else:
                winners = [p for p in players if p != self.rooms[room_id]['game']['dizhu']]
                results = f"农民获胜！胜者：{winners}"
            for p in players:
                self.player_rooms.pop(p, None)
            self.rooms.pop(room_id, None)
            msg +=f"\n游戏结束！{results}，房间已解散"
            return msg
        else:
            idx = players.index(self.rooms[room_id]['game']['current_player'])
            next_players = players[idx+1:] + players[:idx+1]
            for p in next_players:
                if p != self.rooms[room_id]['game']['current_player'] and len(self.rooms[room_id]['game']['hands'][p]) > 0:
                    self.rooms[room_id]['game']['current_player'] = p
                    break
            msg += f"\n轮到玩家: {self.rooms[room_id]['game']['current_player']} 发送【/出牌 []】出牌。"
            return msg

    async def handle_pass(self, room_id, user_id)->str:
        '''
        PASS
        输入 room_id, user_id
        输出 str
        '''
        players = self.rooms[room_id]['players']
        msg,flag = await self.check_game(room_id, user_id)
        if not flag:
            return "校验失败，无法过牌。"
        if not self.rooms[room_id]['game']['last_played']:
            return "首出不能选择不出！"
        idx = players.index(self.rooms[room_id]['game']['current_player'])
        next_players = players[idx+1:] + players[:idx+1]
        for p in next_players:
            if p == self.rooms[room_id]['game']['last_played']['player']:
                self.rooms[room_id]['game']['last_played'] = {}
                self.rooms[room_id]['game']['current_player'] = p
                return f"新一轮开始，轮到玩家: {p} 发送【/出牌 []】出牌。"
            if p != self.rooms[room_id]['game']['current_player'] and len(self.rooms[room_id]['game']['hands'][p]) > 0:
                self.rooms[room_id]['game']['current_player'] = p
                return f"轮到玩家: {p} 发送【/出牌 []】出牌。"
        return msg

    '''-----------------------内部函数--------------------------'''
    async def check_game(self, room_id, user_id):
        players = self.rooms[room_id]['players']
        msg = ''
        if not room_id in self.rooms:
            msg = "没有游戏房间"
            return msg,False
        if user_id not in players:
            msg = "你不在游戏中！"
            return msg,False
        if self.rooms[room_id]['state'] != "playing":
            msg = "游戏尚未开始！"
            return msg,False
        if self.rooms[room_id]['game']['current_player'] != user_id:
            msg = "现在不是你的回合！"
            return msg,False
        return msg,True
    async def bid(self, room_id):
        players = self.rooms[room_id]['players']
        if self.rooms[room_id]['game']['bid_count'] == '3':
            self.rooms[room_id]['game']['dizhu'] = self.rooms[room_id]['game']['current_bidder']
            self.rooms[room_id]['game']['hands'][self.rooms[room_id]['game']['dizhu']].extend(
                self.rooms[room_id]['game']['dipai']
            )
            self.rooms[room_id]['game']['hands'][self.rooms[room_id]['game']['dizhu']].sort(
                key=lambda x: self.card_value(x)
            )
            msg = f"{self.rooms[room_id]['game']['dizhu']} 你是本局游戏的地主！"
            self.rooms[room_id]['state'] = "playing"
            self.rooms[room_id]['game']['current_player'] = self.rooms[room_id]['game']['dizhu']
            msg += f"\n地主确定！游戏开始！\n当前玩家：{self.rooms[room_id]['game']['current_player']} 请出牌"
            await self.look_card(self.rooms[room_id]['game']['dizhu'])
            return msg
        else:
            global op
            idx = players.index(self.rooms[room_id]['game']['current_bidder']) + op
            self.rooms[room_id]['game']['current_robber'] = players[(idx + 1) % 3]
            msg = f"抢地主阶段：请问你是否选择抢地主？当前抢地主玩家：{self.rooms[room_id]['game']['current_robber']}\n发送【/抢地主】抢地主，发送【/不抢】不抢。"
            return msg
    # generate_deck: 类方法，生成一副完整的扑克牌，包括52张普通牌和2张特殊牌（大小王）。
    def generate_deck(self):
        deck = [f"{s}{v}" for v in Poker.values for s in Poker.suits]
        deck += Poker.specials
        return deck

    # card_value: 类方法，返回一张牌的数值大小，用于比较牌的大小。特殊牌（大小王）有更高的数值。
    def card_value(self,card):
        order = {'3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
                 '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13,
                 'A': 14, '2': 15, 'BJ': 16, 'RJ': 17}
        if card in Poker.specials:
            return order[card]
        return order[card[1:]]

    def validate_type(self,cards):
        values = [self.card_value(c) for c in cards]
        values.sort()
        count = len(values)
        value_counts = defaultdict(int)
        for v in values:
            value_counts[v] += 1
        # 火箭
        if set(cards) == {'BJ', 'RJ'}:
            return ('rocket', 17)

        # 炸弹
        if count == 4 and len(set(values)) == 1:
            return ('bomb', values[0])

        # 单牌
        if count == 1:
            return ('single', values[0])

        # 对子
        if count == 2 and len(set(values)) == 1:
            return ('pair', values[0])

        # 三张
        if count == 3 and len(set(values)) == 1:
            return ('triple', values[0])

        # 三带一
        if count == 4:
            counter = defaultdict(int)
            for v in values:
                counter[v] += 1
            if sorted(counter.values()) == [1, 3]:
                return ('triple_plus_single', max(k for k, v in counter.items() if v == 3))

        # 单顺（至少5张）
        if count >= 5 and all(values[i] == values[i - 1] + 1 for i in range(1, count)):
            if max(values) < 15:  # 2不能出现在顺子中
                return ('straight', max(values))

        if count == 5:  # 三带一对的情况
            triples = [v for v, cnt in value_counts.items() if cnt == 3]
            pairs = [v for v, cnt in value_counts.items() if cnt == 2]
            if len(triples) == 1 and len(pairs) == 1:
                return ('triple_plus_pair', triples[0])

        # 双顺（至少3对）
        if count >= 6 and count % 2 == 0:
            pairs = [values[i] for i in range(0, count, 2)]
            if all(pairs[i] == values[2 * i + 1] for i in range(len(pairs))) and \
                    all(pairs[i] == pairs[i - 1] + 1 for i in range(1, len(pairs))) and \
                    max(pairs) < 15:
                return ('double_straight', max(pairs))

        # 四带二
        if count == 6:
            counter = defaultdict(int)
            for v in values:
                counter[v] += 1
            if 4 in counter.values():
                quad_value = max(k for k, v in counter.items() if v == 4)
                return ('quad_plus_two', quad_value)

        # 飞机（至少2组三张）
        if count >= 6 and count % 3 == 0:
            triples = [values[i] for i in range(0, count, 3)]
            if all(triples[i] == triples[i - 1] for i in range(1, len(triples))) and \
                    all(triples[i] == triples[i - 1] + 1 for i in range(1, len(triples))) and \
                    max(triples) < 15:
                return ('airplane', max(triples))

        if count >= 6:
            # 找出所有可能的三张组合
            triple_values = sorted([v for v, cnt in value_counts.items() if cnt >= 3])
            # 寻找最长的连续三张序列
            max_sequence = []
            current_seq = []
            for v in triple_values:
                if not current_seq or v == current_seq[-1] + 1:
                    current_seq.append(v)
                else:
                    if len(current_seq) > len(max_sequence):
                        max_sequence = current_seq
                    current_seq = [v]
                if v >= 15:  # 2和王不能出现在三顺中
                    current_seq = []
                    break
            if len(current_seq) > len(max_sequence):
                max_sequence = current_seq

            if len(max_sequence) >= 2:
                # 计算实际使用的三张牌
                used_triples = []
                for v in max_sequence:
                    used_triples.extend([v] * 3)

                # 剩余牌必须是翅膀（单或对）
                remaining = []
                for v in values:
                    if v in max_sequence and used_triples.count(v) > 0:
                        used_triples.remove(v)
                    else:
                        remaining.append(v)

                # 翅膀数量必须等于三顺数量或两倍三顺数量
                if len(remaining) not in [len(max_sequence), 2 * len(max_sequence)]:
                    return (None, 0)

                # 翅膀类型判断
                wing_counts = defaultdict(int)
                for v in remaining:
                    wing_counts[v] += 1

                if len(remaining) == len(max_sequence):
                    # 翅膀必须是单牌
                    for v, cnt in wing_counts.items():
                        if cnt != 1:
                            return (None, 0)
                elif len(remaining) == 2 * len(max_sequence):
                    # 翅膀必须是对子
                    for v, cnt in wing_counts.items():
                        if cnt != 2:
                            return (None, 0)

                return ('airplane_with_wings', max(max_sequence))

        return (None, 0)

    def compare_plays(self, last_type, new_type):
        type_order = ['single', 'pair', 'triple', 'straight',
                      'double_straight', 'airplane', 'triple_plus_single',
                      'triple_plus_pair', 'quad_plus_two', 'bomb', 'rocket']
        if last_type[0] == 'rocket':
            return False
        if new_type[0] == 'rocket':
            return True
        if last_type[0] == 'bomb' and new_type[0] == 'bomb':
            return new_type[1] > last_type[1]
        if last_type[0] == 'bomb' and new_type[0] != 'bomb':
            return False
        if new_type[0] == 'bomb':
            return True
        if last_type[0] != new_type[0]:
            return False
        return new_type[1] > last_type[1]

    def parse_cards(self, input_str, hand):
        card_values = self.convert_input(input_str)
        if not card_values:
            return None
        required = defaultdict(int)
        for v in card_values:
            required[v] += 1
        candidates = self.group_by_value(hand)
        matched = []
        for value, count in required.items():
            if value not in candidates or len(candidates[value]) < count:
                return None
            matched.append(candidates[value][:count])
        result = [card for group in matched for card in group]
        return sorted(result, key=lambda x: self.card_value(x))

    def convert_input(self, input_str):
        convert_map = {
            'bj': 'BJ', 'rj': 'RJ',
            'j': 'J', 'q': 'Q', 'k': 'K', 'a': 'A',
            '0': '10', '1': '10',
            '2': '2', '3': '3', '4': '4', '5': '5',
            '6': '6', '7': '7', '8': '8', '9': '9'
        }
        values = []
        i = 0
        while i < len(input_str):
            char = input_str[i].lower()
            if char == '1' and i + 1 < len(input_str) and input_str[i + 1] in ('0', 'o'):
                values.append('10')
                i += 2
                continue
            if char == '0':
                values.append('10')
                i += 1
                continue
            if char in ('小','大') and i + 1 < len(input_str):
                next_char = input_str[i + 1].lower()
                if char == '大' and next_char == '王':
                    values.append('BJ')
                    i += 2
                    continue
                if char == '小' and next_char == '王':
                    values.append('RJ')
                    i += 2
                    continue
            converted = convert_map.get(char)
            if not converted:
                return None
            values.append(converted)
            i += 1
        return values

    def group_by_value(self, hand):
        groups = defaultdict(list)
        for card in hand:
            if card in ['BJ', 'RJ']:
                value = card
            else:
                value = card[1:] if card[0] in Poker.suits else card
            groups[value].append(card)
        for v in groups.values():
            v.sort(key=lambda x: Poker.suits.index(x[0]) if x[0] in Poker.suits else 0)
        return groups

    async def generate_hand_image(self,cards,idx):
        font = './data/plugins/astrbot_plugin_comp_entertainment/msyh.ttf'
        output_path = f"./data/plugins/astrbot_plugin_comp_entertainment/pic{idx}.png"
        card_width = 80
        card_height = 120
        spacing = 50
        img = Image.new('RGB', (max(card_width + (len(cards) - 1) * spacing, 500), 200), (56, 94, 15))
        d = ImageDraw.Draw(img)
        text = "【斗地主手牌】"
        bbox = d.textbbox((0, 0), text, font=ImageFont.truetype(font, 50))
        text_width = bbox[2] - bbox[0]  # 文本宽度
        x = (img.width - text_width) / 2  # 水平居中
        d.text((x, 0), text, fill=(0, 0, 0), font=ImageFont.truetype(font, 50))
        for i, card in enumerate(cards):
            if card in ['BJ', 'RJ']:
                color = (255, 0, 0) if card == 'BJ' else (0, 0, 0)
                card_img = Image.new('RGB', (card_width, card_height), (255, 255, 255))
                d = ImageDraw.Draw(card_img)
                x, y = 10, 0
                for char in 'JOKER':
                    # 获取字符的边界框
                    bbox = d.textbbox((x, y), char, font=ImageFont.truetype(font, 20))
                    char_width, char_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
                    # 绘制字符
                    d.text((x, y), char, fill=color, font=ImageFont.truetype(font, 20))
                    # 调整 y 坐标
                    y += char_height + 5
            else:
                suit = card[0]
                value = card[1:]
                card_img = Image.new('RGB', (card_width, card_height), (255, 255, 255))
                d = ImageDraw.Draw(card_img)
                d.text((5, 60), suit, fill=Poker.colors[suit], font=ImageFont.truetype('arial.ttf', 50))
                d.text((5, 0), value, fill=(0, 0, 0), font=ImageFont.truetype(font, 40))
            border_width = 1
            border_color = (0, 0, 0)  # 红色边框
            bordered_img = ImageOps.expand(card_img, border=border_width, fill=border_color)
            img.paste(bordered_img, (i * spacing, 80))
        img.save(output_path, format='PNG')
        return output_path

    def load_game(self):
        dicts = []
        with open(self.ddzpath, 'r') as f:
            for line in f:
                dicts.append(json.loads(line.strip()))
        if not dicts:
            # logger.warning("加载的数据为空")
            return
        else:
            self.rooms = dicts[0]
            self.player_rooms = dicts[1]
            return

    def save_game(self):
        with open(self.ddzpath, 'w') as f:
            for d in [self.rooms, self.player_rooms]:
                f.write(json.dumps(d) + '\n')

class Poker:
    suits = ['♠', '♥', '♦', '♣']
    values = ['3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A', '2']
    specials = ['BJ', 'RJ']
    colors = {'♠': (0, 0, 0), '♥': (255, 0, 0),
              '♦': (255, 0, 0), '♣': (0, 0, 0)}

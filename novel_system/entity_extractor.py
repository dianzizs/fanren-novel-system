"""
实体抽取模块

用于从文本中抽取实体属性并检测矛盾。
共享于 AnswerValidator 和 ContinuationValidator。

设计原则：
1. 预编译所有正则模式以优化性能
2. 词库提供候选词，正则模式提供上下文约束
3. 支持否定词检测以避免误匹配
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ExtractedAttribute:
    """从文本中抽取的属性"""
    attr_type: str  # "personality", "appearance", "body_type", "color", "cultivation"
    value: str
    context: str = ""  # 周围上下文
    start_pos: int = 0  # 匹配起始位置
    negated: bool = False  # 是否被否定


@dataclass
class EntityAttributes:
    """单个实体的属性集合"""
    name: str
    entity_type: str = "person"
    attributes: dict[str, ExtractedAttribute] = field(default_factory=dict)


class EntityExtractor:
    """
    实体抽取器

    使用预编译正则模式和词库抽取实体属性，检测属性矛盾。
    """

    # ═══════════ 已知人名（可扩展）═══════════
    KNOWN_PERSONS = {
        # 凡人修仙传主要人物
        "韩立", "南宫婉", "厉飞雨", "墨大夫", "墨居仁", "李化元",
        "张铁", "韩胖子", "董萱儿", "陈巧倩", "曲魂", "贾天龙",
        "岳堂主", "王门主", "万小山", "赵子灵", "张长贵",
        "银月", "元刹", "冰凤", "金童", "噬金虫",
    }

    # 人名抽取模式
    PERSON_PATTERNS = [
        r'([\u4e00-\u9fa5]{2,4})(?=说道?|笑道|皱眉|点头|摇头|沉声道|冷声道|叹道)',
    ]

    # ═══════════ 性格对立词库（15个谱系，60+组）═══════════
    PERSONALITY_OPPOSITES = {
        # 谨慎-鲁莽谱系
        "谨慎": ["轻率", "鲁莽", "冒失", "粗心", "马虎", "大意", "莽撞"],
        "小心": ["鲁莽", "冒失", "轻率", "大意"],
        "慎重": ["轻率", "莽撞", "草率"],
        "稳重": ["轻浮", "浮躁", "莽撞", "草率"],
        "细致": ["粗心", "马虎", "草率"],
        "严谨": ["随意", "马虎", "草率"],
        "周全": ["粗疏", "疏漏"],

        # 内外向谱系
        "外向": ["内向", "孤僻", "害羞", "腼腆"],
        "开朗": ["内向", "孤僻", "沉闷", "忧郁", "郁郁寡欢"],
        "活泼": ["沉闷", "死板", "呆板", "木讷"],
        "豪爽": ["谨慎", "小心", "拘谨", "内向", "小气"],
        "健谈": ["寡言", "沉默", "内向"],
        "合群": ["孤僻", "不合群", "孤芳自赏"],

        # 情绪稳定性谱系
        "冷静": ["急躁", "冲动", "焦躁", "浮躁", "暴躁"],
        "沉稳": ["浮躁", "轻浮", "急躁", "冲动"],
        "平和": ["暴躁", "易怒", "冲动"],
        "温和": ["暴躁", "凶狠", "严厉", "凶残"],
        "温柔": ["暴躁", "凶狠", "粗暴", "冷酷"],
        "耐心": ["急躁", "烦躁", "不耐烦"],

        # 冷暖谱系
        "热情": ["冷漠", "冷淡", "孤僻", "无情"],
        "热心": ["冷漠", "冷淡", "无情", "自私"],
        "亲切": ["冷漠", "冷淡", "疏远"],
        "温暖": ["冷漠", "冷酷", "冰冷"],
        "冷漠": ["热情", "热心", "亲切", "温暖", "友善"],
        "冷淡": ["热情", "热心", "关切"],

        # 正直-狡诈谱系
        "正直": ["阴险", "狡诈", "圆滑", "虚伪"],
        "诚实": ["虚伪", "狡猾", "欺诈", "虚假"],
        "真诚": ["虚伪", "虚假", "矫情"],
        "坦率": ["城府", "阴险", "虚伪", "矫揉造作"],
        "狡猾": ["正直", "老实", "淳朴", "憨厚", "诚实"],
        "狡诈": ["正直", "诚实", "忠厚", "善良"],
        "阴险": ["正直", "善良", "光明磊落", "坦荡"],
        "城府": ["单纯", "直率", "坦诚", "天真"],
        "虚伪": ["真诚", "真实", "诚实"],

        # 善恶谱系
        "善良": ["残忍", "狠毒", "恶毒", "凶狠", "邪恶"],
        "仁慈": ["残忍", "冷酷", "无情", "凶残"],
        "宽厚": ["刻薄", "尖酸", "苛刻"],
        "宽容": ["狭隘", "斤斤计较", "睚眦必报"],
        "残忍": ["善良", "仁慈", "慈悲", "宽厚"],
        "刻薄": ["宽厚", "厚道", "宽容"],

        # 勇怯谱系
        "勇敢": ["胆小", "懦弱", "怯懦", "畏缩", "胆怯"],
        "大胆": ["胆小", "怯懦", "畏首畏尾", "畏缩"],
        "无畏": ["胆怯", "怯懦", "畏缩"],
        "果断": ["犹豫", "优柔寡断", "拖泥带水"],
        "胆小": ["勇敢", "大胆", "无畏"],
        "懦弱": ["勇敢", "坚强", "刚强"],
        "优柔寡断": ["果断", "干脆", "决断"],

        # 智愚谱系
        "聪明": ["愚笨", "愚蠢", "笨拙", "迟钝", "愚昧"],
        "机敏": ["迟钝", "愚钝", "木讷", "呆板"],
        "睿智": ["愚昧", "无知", "浅薄"],
        "灵活": ["死板", "固执", "僵化"],
        "憨厚": ["狡猾", "精明", "圆滑", "狡诈"],
        "愚笨": ["聪明", "机敏", "智慧"],
        "迟钝": ["机敏", "灵敏", "敏捷"],

        # 独立-依赖谱系
        "独立": ["依赖", "依附", "软弱"],
        "自立": ["依赖", "依附"],
        "坚强": ["软弱", "脆弱", "懦弱"],
        "依赖": ["独立", "自主", "自强"],
        "脆弱": ["坚强", "刚强", "坚韧"],

        # 乐观-悲观谱系
        "乐观": ["悲观", "消极", "忧郁", "沮丧"],
        "积极": ["消极", "颓废", "消沉"],
        "向上": ["颓废", "堕落", "消沉"],
        "悲观": ["乐观", "积极", "豁达"],
        "忧郁": ["开朗", "乐观", "阳光"],

        # 成熟谱系
        "成熟": ["幼稚", "孩子气", "单纯"],
        "老练": ["稚嫩", "青涩", "天真"],
        "深沉": ["浅薄", "肤浅", "浮躁"],
        "幼稚": ["成熟", "稳重", "老成"],
        "单纯": ["城府", "复杂", "老练"],

        # 勤惰谱系
        "勤奋": ["懒惰", "懒散", "怠惰", "好逸恶劳"],
        "勤劳": ["懒惰", "游手好闲"],
        "刻苦": ["懒散", "懈怠"],
        "懒惰": ["勤奋", "勤劳", "刻苦"],
        "懈怠": ["勤奋", "努力", "刻苦"],

        # 自信谱系
        "自信": ["自卑", "怯懦", "畏缩"],
        "自负": ["谦虚", "谦逊", "低调"],
        "谦虚": ["自负", "骄傲", "狂妄"],
        "骄傲": ["谦虚", "谦逊", "虚心"],
        "自卑": ["自信", "自强"],

        # 处事风格谱系
        "大方": ["小气", "吝啬", "抠门"],
        "慷慨": ["吝啬", "小气", "自私"],
        "洒脱": ["拘谨", "拘束", "放不开"],
        "干脆": ["拖沓", "优柔寡断", "婆婆妈妈"],
        "小气": ["大方", "慷慨", "豪爽"],
        "吝啬": ["大方", "慷慨", "豪爽"],
    }

    # ═══════════ 颜色对立词库 ═══════════
    COLOR_OPPOSITES = {
        # 基本色对立
        "黑": ["白", "金", "银", "苍白"],
        "白": ["黑", "灰", "黝黑", "漆黑", "墨黑"],
        "金": ["黑", "银", "铁"],
        "银": ["金", "黑", "黄"],

        # 暖冷色对立
        "红": ["青", "蓝", "绿", "白"],
        "赤": ["青", "蓝", "白"],
        "朱": ["青", "蓝"],
        "绯": ["青", "蓝"],
        "殷": ["青", "蓝"],
        "橙": ["蓝", "紫"],
        "黄": ["紫", "蓝", "黑"],
        "金黄": ["紫", "墨黑"],
        "杏黄": ["紫", "深蓝"],

        # 冷色系内部对立
        "青": ["红", "赤", "橙"],
        "蓝": ["红", "橙", "黄"],
        "湛蓝": ["橙红", "朱红"],
        "海蓝": ["橙红", "金黄"],
        "绿": ["红", "紫"],
        "翠绿": ["红", "紫红"],
        "墨绿": ["粉红", "桃红"],

        # 紫色系对立
        "紫": ["黄", "橙", "绿"],
        "紫红": ["翠绿", "嫩绿"],

        # 灰色系对立
        "灰": ["白", "黑", "纯白"],
        "银灰": ["金红", "橙红"],

        # 粉色系对立
        "粉": ["深红", "墨黑", "深紫"],
        "粉红": ["深绿", "墨绿"],

        # 肤色相关
        "黝黑": ["白皙", "苍白", "粉白"],
        "白皙": ["黝黑", "漆黑", "古铜"],
        "古铜": ["苍白", "粉白", "白皙"],
    }

    # ═══════════ 体型对立词库 ═══════════
    BODY_TYPE_KEYWORDS = {
        # 高矮谱系
        "高大": ["矮小", "瘦小", "矮", "矮短", "矮胖"],
        "修长": ["矮胖", "臃肿", "矮短", "粗短"],
        "挺拔": ["佝偻", "驼背", "矮小"],
        "高挑": ["矮胖", "矮墩", "矮短"],

        # 壮弱谱系
        "魁梧": ["瘦弱", "纤细", "单薄", "瘦削", "干瘦"],
        "壮硕": ["瘦弱", "纤细", "瘦削", "干瘪"],
        "健壮": ["瘦弱", "虚弱", "病弱"],
        "结实": ["虚弱", "单薄", "瘦弱"],
        "强壮": ["虚弱", "孱弱", "瘦弱"],

        # 胖瘦谱系
        "消瘦": ["肥胖", "壮硕", "魁梧", "臃肿", "肥硕"],
        "纤细": ["粗壮", "魁梧", "壮硕", "肥胖", "臃肿"],
        "苗条": ["肥胖", "臃肿", "壮硕", "肥硕", "肥壮"],
        "瘦削": ["肥胖", "壮硕", "臃肿", "肥硕"],
        "干瘦": ["肥胖", "肥硕", "丰腴", "丰满"],
        "清瘦": ["肥胖", "肥硕", "丰腴"],

        # 肥胖谱系
        "肥胖": ["消瘦", "瘦弱", "纤细", "苗条", "清瘦"],
        "臃肿": ["苗条", "纤细", "修长", "消瘦"],
        "肥硕": ["瘦削", "纤细", "苗条", "清瘦"],
        "丰腴": ["干瘦", "消瘦", "瘦削"],
        "丰满": ["干瘦", "消瘦", "干瘪"],

        # 特殊体型
        "匀称": ["臃肿", "畸形", "不协调"],
        "单薄": ["魁梧", "壮硕", "结实", "健壮"],
    }

    # ═══════════ 五官对立词库 ═══════════
    FACIAL_FEATURES = {
        # 面容俊美谱系
        "英俊": ["丑陋", "难看", "面目可憎", "狰狞", "凶恶"],
        "俊朗": ["丑陋", "难看", "狰狞", "凶恶"],
        "俊美": ["丑陋", "难看", "凶恶", "可憎"],
        "俊秀": ["丑陋", "难看", "粗鄙"],
        "秀美": ["丑陋", "粗犷", "凶悍", "狰狞"],
        "清秀": ["粗犷", "凶悍", "狰狞", "粗俗"],
        "俊俏": ["丑陋", "难看", "粗鄙"],

        # 美貌谱系
        "美貌": ["丑陋", "难看", "平庸", "丑怪"],
        "漂亮": ["丑陋", "难看", "平庸"],
        "绝美": ["丑陋", "难看", "平庸", "普通"],
        "惊艳": ["平庸", "普通", "丑陋"],
        "美如冠玉": ["獐头鼠目", "尖嘴猴腮", "面目可憎"],
        "眉清目秀": ["獐头鼠目", "尖嘴猴腮", "青面獠牙"],

        # 相貌普通谱系
        "相貌平平": ["英俊", "俊朗", "俊美", "帅气", "美貌", "绝美", "惊艳", "俊俏"],
        "相貌普通": ["英俊", "俊朗", "绝美", "美貌", "俊美"],
        "相貌端正": ["丑陋", "狰狞", "歪瓜裂枣"],
        "其貌不扬": ["英俊", "俊朗", "俊美", "出众"],
        "相貌堂堂": ["猥琐", "丑陋", "尖嘴猴腮"],

        # 丑陋谱系
        "丑陋": ["英俊", "俊朗", "俊美", "美貌", "漂亮", "俊俏", "秀美"],
        "难看": ["英俊", "俊朗", "俊美", "美貌", "漂亮", "俊俏"],
        "面目可憎": ["英俊", "俊朗", "俊美", "慈眉善目"],
        "狰狞": ["俊美", "俊朗", "秀美", "慈眉善目"],
        "凶恶": ["俊美", "俊朗", "秀美", "慈祥"],
        "青面獠牙": ["眉清目秀", "慈眉善目", "面容俊秀"],
        "獐头鼠目": ["眉清目秀", "相貌堂堂", "一表人才"],
        "尖嘴猴腮": ["相貌堂堂", "一表人才", "俊朗"],

        # 气质面容谱系
        "慈眉善目": ["凶神恶煞", "青面獠牙", "面目可憎"],
        "慈祥": ["凶恶", "狰狞", "凶狠"],
        "威严": ["猥琐", "卑微", "怯懦"],
        "英气": ["猥琐", "怯懦", "畏缩"],
        "猥琐": ["英气", "俊朗", "威严", "堂堂"],

        # 脸型谱系
        "瓜子脸": ["方脸", "圆脸", "大饼脸", "国字脸"],
        "鹅蛋脸": ["方脸", "长脸", "大饼脸"],
        "脸庞清秀": ["脸庞粗犷", "面相凶恶"],
        "面容清癯": ["面容丰腴", "肥头大耳"],
        "面容丰润": ["面容枯槁", "面黄肌瘦"],
        "肥头大耳": ["尖嘴猴腮", "面容清癯", "瘦骨嶙峋"],

        # 肤色谱系
        "白皙": ["黝黑", "漆黑", "古铜", "黧黑"],
        "粉白": ["黝黑", "漆黑", "黧黑"],
        "红润": ["苍白", "惨白", "蜡黄", "青白"],
        "苍白": ["红润", "健康", "红光满面"],
        "黝黑": ["白皙", "苍白", "粉白", "白嫩"],

        # 眉眼谱系
        "浓眉大眼": ["贼眉鼠眼", "细眉小眼", "鼠目寸光"],
        "剑眉星目": ["贼眉鼠眼", "猥琐"],
        "眉目如画": ["獐头鼠目", "尖嘴猴腮"],
        "明眸皓齿": ["青面獠牙", "尖嘴猴腮"],
        "贼眉鼠眼": ["浓眉大眼", "剑眉星目", "眉清目秀"],

        # 鼻型谱系
        "高鼻梁": ["塌鼻梁", "塌鼻子", "塌鼻"],
        "鼻如悬胆": ["塌鼻梁", "蒜头鼻", "朝天鼻"],
        "挺鼻": ["塌鼻", "塌鼻子"],

        # 嘴型谱系
        "樱桃小嘴": ["血盆大口", "大嘴", "阔嘴"],
        "唇红齿白": ["青面獠牙", "尖嘴猴腮"],
        "血盆大口": ["樱桃小嘴", "小嘴", "薄唇"],
    }

    # ═══════════ 修为等级体系 ═══════════
    CULTIVATION_LEVELS = [
        "炼气期", "筑基期", "结丹期", "元婴期", "化神期",
        "炼虚期", "合体期", "大乘期", "渡劫期",
    ]

    # ═══════════ 正则模式定义 ═══════════
    # 性格属性正则模式
    PERSONALITY_PATTERNS = [
        r'(?:性格|性情|为人|品性)(?:是|为|比较)?(?:很|颇|十分|非常)?({personality_words})',
        r'为人(?:很|颇|十分|非常)?({personality_words})',
        r'({personality_words})(?:的|之)(?:性格|性情|品性)',
        r'({personality_words})(?:型)?(?:的)?人',
    ]

    # 外貌属性正则模式
    APPEARANCE_PATTERNS = [
        r'(?:相貌|面容|长相|容貌|脸庞)(?:是|为|比较)?(?:很|颇|十分|非常)?({appearance_words})',
        r'相貌({appearance_words})',
        r'(?:面容|脸庞|面孔)(?:很|颇|十分|非常)?({appearance_words})',
        r'一副({appearance_words})(?:的)?(?:面孔|面容|长相)',
    ]

    # 体型正则模式
    BODY_TYPE_PATTERNS = [
        r'(?:身材|体格|体形)(?:是|为|比较)?(?:很|颇|十分|非常)?({body_words})',
        r'({body_words})(?:的)?(?:身材|体格|身形)',
        r'长得(?:很|颇|十分|非常)?({body_words})',
        r'(?:身材|个子)(?:很|颇|十分|非常)?({body_words})',
    ]

    # 颜色特征正则模式
    COLOR_PATTERNS = [
        r'({color_words})(?:色)?(?:的)?(?:头发|长发|短发|青丝)',
        r'({color_words})(?:色)?(?:的)?(?:眼睛|眼眸|瞳孔|眸子)',
        r'(?:皮肤|肤色)(?:是|为)?(?:很|颇|十分)?({color_words})',
        r'({color_words})(?:色)?(?:的)?(?:皮肤|肌肤)',
    ]

    # 修为等级正则模式
    CULTIVATION_PATTERNS = [
        r'({cultivation_levels})(?:期)?(?:修士|高手|强者|修仙者)',
        r'修为(?:已|已经|达到|突破|晋升)?(?:至|到)?({cultivation_levels})',
        r'(?:已是|已经是|达到)({cultivation_levels})',
    ]

    # 否定词模式
    NEGATION_PATTERNS = [
        r'不(?:是|算|能说)',
        r'并非',
        r'不是(?:那种)?',
        r'没(?:有)?',
        r'谈不上',
        r'算不上',
    ]

    def __init__(self):
        """初始化：预编译所有正则模式"""
        # 从词库动态生成正则表达式词组
        personality_words = '|'.join(re.escape(k) for k in self.PERSONALITY_OPPOSITES.keys())
        appearance_words = '|'.join(re.escape(k) for k in self.FACIAL_FEATURES.keys())
        body_words = '|'.join(re.escape(k) for k in self.BODY_TYPE_KEYWORDS.keys())
        color_words = '|'.join(re.escape(k) for k in self.COLOR_OPPOSITES.keys())
        cultivation_levels = '|'.join(re.escape(l) for l in self.CULTIVATION_LEVELS)

        # 编译性格正则
        self._personality_re = [
            re.compile(p.format(personality_words=personality_words))
            for p in self.PERSONALITY_PATTERNS
        ]

        # 编译外貌正则
        self._appearance_re = [
            re.compile(p.format(appearance_words=appearance_words))
            for p in self.APPEARANCE_PATTERNS
        ]

        # 编译体型正则
        self._body_re = [
            re.compile(p.format(body_words=body_words))
            for p in self.BODY_TYPE_PATTERNS
        ]

        # 编译颜色正则
        self._color_re = [
            re.compile(p.format(color_words=color_words))
            for p in self.COLOR_PATTERNS
        ]

        # 编译修为等级正则
        self._cultivation_re = [
            re.compile(p.format(cultivation_levels=cultivation_levels))
            for p in self.CULTIVATION_PATTERNS
        ]

        # 编译否定词正则
        self._negation_re = [
            re.compile(p) for p in self.NEGATION_PATTERNS
        ]

        # 编译已知人名正则
        known_pattern = '|'.join(re.escape(p) for p in self.KNOWN_PERSONS)
        self._known_person_re = re.compile(f'({known_pattern})')

        # 编译人名模式正则
        self._person_pattern_re = [
            re.compile(p) for p in self.PERSON_PATTERNS
        ]

    def extract_entities(self, text: str) -> list[EntityAttributes]:
        """
        从文本中抽取实体（人物）

        Args:
            text: 输入文本

        Returns:
            实体列表
        """
        entities = []
        seen = set()

        # 首先检查已知人名
        for match in self._known_person_re.finditer(text):
            name = match.group(1)
            if name not in seen:
                entities.append(EntityAttributes(name=name, entity_type="person"))
                seen.add(name)

        # 然后使用模式匹配
        for pattern in self._person_pattern_re:
            for match in pattern.finditer(text):
                name = match.group(1)
                if name not in seen and len(name) >= 2:
                    entities.append(EntityAttributes(name=name, entity_type="person"))
                    seen.add(name)

        return entities

    def extract_attributes(
        self,
        text: str,
        entity_name: Optional[str] = None,
    ) -> dict[str, ExtractedAttribute]:
        """
        从文本中抽取属性

        Args:
            text: 输入文本
            entity_name: 可选的实体名称，用于限定上下文

        Returns:
            属性字典 {attr_type: ExtractedAttribute}
        """
        attributes = {}

        # 如果指定了实体名，找到实体附近的上下文
        context_window = 100
        search_text = text
        if entity_name:
            # 查找实体名位置，使用附近的上下文
            pos = text.find(entity_name)
            if pos != -1:
                start = max(0, pos - context_window)
                end = min(len(text), pos + len(entity_name) + context_window)
                search_text = text[start:end]

        # 抽取性格属性
        personality_attr = self._extract_by_patterns(
            search_text, self._personality_re, "personality"
        )
        if personality_attr:
            attributes["personality"] = personality_attr

        # 抽取外貌属性
        appearance_attr = self._extract_by_patterns(
            search_text, self._appearance_re, "appearance"
        )
        if appearance_attr:
            attributes["appearance"] = appearance_attr

        # 抽取体型属性
        body_attr = self._extract_by_patterns(
            search_text, self._body_re, "body_type"
        )
        if body_attr:
            attributes["body_type"] = body_attr

        # 抽取颜色属性
        color_attr = self._extract_by_patterns(
            search_text, self._color_re, "color"
        )
        if color_attr:
            attributes["color"] = color_attr

        # 抽取修为等级
        cultivation_attr = self._extract_by_patterns(
            search_text, self._cultivation_re, "cultivation"
        )
        if cultivation_attr:
            attributes["cultivation"] = cultivation_attr

        return attributes

    def _extract_by_patterns(
        self,
        text: str,
        patterns: list[re.Pattern],
        attr_type: str,
    ) -> Optional[ExtractedAttribute]:
        """使用正则模式抽取属性"""
        for pattern in patterns:
            for match in pattern.finditer(text):
                value = match.group(1)
                start_pos = match.start()

                # 检查是否被否定
                negated = self._check_negation(text, start_pos)

                # 获取上下文
                ctx_start = max(0, start_pos - 10)
                ctx_end = min(len(text), match.end() + 10)
                context = text[ctx_start:ctx_end]

                return ExtractedAttribute(
                    attr_type=attr_type,
                    value=value,
                    context=context,
                    start_pos=start_pos,
                    negated=negated,
                )
        return None

    def _check_negation(self, text: str, match_start: int) -> bool:
        """检查匹配位置前是否有否定词"""
        prefix = text[max(0, match_start - 20):match_start]
        for neg_pattern in self._negation_re:
            if neg_pattern.search(prefix):
                return True
        return False

    def check_contradiction(
        self,
        attr_type: str,
        value1: str,
        value2: str,
    ) -> tuple[bool, Optional[str]]:
        """
        检查两个属性值是否矛盾

        Args:
            attr_type: 属性类型
            value1: 第一个值（如证据中的值）
            value2: 第二个值（如答案/续写中的值）

        Returns:
            (是否矛盾, 矛盾说明)
        """
        if attr_type == "personality":
            return self._check_personality_contradiction(value1, value2)
        elif attr_type in ("appearance", "body_type"):
            return self._check_appearance_contradiction(value1, value2)
        elif attr_type == "color":
            return self._check_color_contradiction(value1, value2)
        elif attr_type == "cultivation":
            return self._check_cultivation_contradiction(value1, value2)
        return False, None

    def _check_personality_contradiction(
        self,
        value1: str,
        value2: str,
    ) -> tuple[bool, Optional[str]]:
        """检查性格矛盾"""
        for trait, opposites in self.PERSONALITY_OPPOSITES.items():
            # 检查 value1 包含 trait 且 value2 包含对立词
            if trait in value1:
                for opp in opposites:
                    if opp in value2:
                        return True, f"'{trait}' 与 '{opp}' 性格对立"
            # 反向检查
            if trait in value2:
                for opp in opposites:
                    if opp in value1:
                        return True, f"'{trait}' 与 '{opp}' 性格对立"
        return False, None

    def _check_appearance_contradiction(
        self,
        value1: str,
        value2: str,
    ) -> tuple[bool, Optional[str]]:
        """检查外貌矛盾（包括五官和体型）"""
        # 检查五官矛盾
        for feature, opposites in self.FACIAL_FEATURES.items():
            if feature in value1:
                for opp in opposites:
                    if opp in value2:
                        return True, f"'{feature}' 与 '{opp}' 外貌矛盾"
            if feature in value2:
                for opp in opposites:
                    if opp in value1:
                        return True, f"'{feature}' 与 '{opp}' 外貌矛盾"

        # 检查体型矛盾
        for body_type, opposites in self.BODY_TYPE_KEYWORDS.items():
            if body_type in value1:
                for opp in opposites:
                    if opp in value2:
                        return True, f"'{body_type}' 与 '{opp}' 体型矛盾"
            if body_type in value2:
                for opp in opposites:
                    if opp in value1:
                        return True, f"'{body_type}' 与 '{opp}' 体型矛盾"

        return False, None

    def _check_color_contradiction(
        self,
        value1: str,
        value2: str,
    ) -> tuple[bool, Optional[str]]:
        """检查颜色矛盾"""
        for color, opposites in self.COLOR_OPPOSITES.items():
            if color in value1:
                for opp in opposites:
                    if opp in value2:
                        return True, f"颜色 '{color}' 与 '{opp}' 矛盾"
            if color in value2:
                for opp in opposites:
                    if opp in value1:
                        return True, f"颜色 '{color}' 与 '{opp}' 矛盾"
        return False, None

    def _check_cultivation_contradiction(
        self,
        value1: str,
        value2: str,
    ) -> tuple[bool, Optional[str]]:
        """检查修为等级矛盾（跳跃过大）"""
        idx1 = self.get_cultivation_level_index(value1)
        idx2 = self.get_cultivation_level_index(value2)

        if idx1 == -1 or idx2 == -1:
            return False, None

        # 如果等级跳跃超过2级，认为有矛盾
        if abs(idx2 - idx1) > 2:
            return True, f"修为等级从 '{value1}' 跳跃到 '{value2}' 差距过大"

        return False, None

    def get_cultivation_level_index(self, text: str) -> int:
        """
        获取修为等级索引

        Args:
            text: 包含修为等级的文本

        Returns:
            等级索引，未找到返回 -1
        """
        for i, level in enumerate(self.CULTIVATION_LEVELS):
            if level in text:
                return i
        return -1

    def check_entity_consistency(
        self,
        text1: str,
        text2: str,
        entity_name: str,
    ) -> list[str]:
        """
        检查同一实体在两段文本中的属性一致性

        Args:
            text1: 第一段文本（如证据）
            text2: 第二段文本（如答案/续写）
            entity_name: 实体名称

        Returns:
            矛盾问题列表
        """
        issues = []

        # 从两段文本中抽取属性
        attrs1 = self.extract_attributes(text1, entity_name)
        attrs2 = self.extract_attributes(text2, entity_name)

        # 对比检查矛盾
        for attr_type, attr2 in attrs2.items():
            if attr2.negated:
                continue  # 被否定的属性不参与对比

            attr1 = attrs1.get(attr_type)
            if attr1 is None:
                continue

            if attr1.negated:
                continue

            is_contradiction, explanation = self.check_contradiction(
                attr_type, attr1.value, attr2.value
            )

            if is_contradiction:
                issues.append(
                    f"'{entity_name}' 的{attr_type}描述矛盾："
                    f"原文为 '{attr1.value}'，此处为 '{attr2.value}'（{explanation}）"
                )

        return issues


# 单例实例
_extractor_instance: Optional[EntityExtractor] = None


def get_extractor() -> EntityExtractor:
    """获取 EntityExtractor 单例实例"""
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = EntityExtractor()
    return _extractor_instance

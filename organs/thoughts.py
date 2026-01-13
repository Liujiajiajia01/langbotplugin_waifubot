import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class Thoughts:
    """思维系统"""
    def __init__(self, plugin):
        self.plugin = plugin
        self.memory = None
        self.generator = None

    def initialize(self):
        """
        初始化思维系统
        """
        from ..cells.generator import Generator
        self._generator = Generator(self.plugin)

    async def _analyze_person_conversations(self, memory, profile: str, background: str, manner: str) -> str:
        """
        分析私信对话
        :param memory: 记忆系统实例
        :param profile: 角色简介
        :param background: 角色背景
        :param manner: 行为准则
        :return: 分析结果
        """
        if not hasattr(memory, 'short_term_memory') or not hasattr(memory, 'analyze_max_conversations'):
            return ""
            
        conversations = memory.short_term_memory[-memory.analyze_max_conversations:]
        if not conversations:
            return ""
            
        # 简化版的对话分析
        last_message = conversations[-1]
        last_content = last_message.get('content', '')
        last_speaker = last_message.get('speaker', '')
        
        # 构建分析提示
        user_prompt = f"分析用户说的话：'{last_content}'，站在助手的角度思考用户的意图。"
        if profile:
            user_prompt += f" 角色设定：{profile}"
        if background:
            user_prompt += f" 背景信息：{background}"
        if manner:
            user_prompt += f" 行为准则：{manner}"
        user_prompt += f" 分析结果要简明扼要，不超过30个字。"
        
        # 调用生成器生成分析结果
        analysis_result = await self._generator.generate_response(user_prompt)
        return analysis_result.strip()

    async def generate_person_prompt(self, memory, card) -> Tuple[str, str]:
        """
        生成私信提示
        :param memory: 记忆系统实例
        :param card: 角色卡实例
        :return: 提示和分析结果
        """
        if not hasattr(memory, 'short_term_memory'):
            return "", ""
            
        conversations = memory.short_term_memory
        if not conversations:
            return "", ""
            
        # 获取最近的对话内容
        recent_conversations = conversations[-5:]  # 最近5条消息
        conversation_str = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in recent_conversations])
        
        # 获取角色信息
        profile = " ".join(card.get_profile())
        background = " ".join(card.get_background())
        manner = " ".join(card.get_rules())
        
        # 生成分析
        analysis = ""
        if hasattr(memory, 'conversation_analysis_flag') and memory.conversation_analysis_flag:
            analysis = await self._analyze_person_conversations(memory, profile, background, manner)
            logger.debug(f"对话分析结果: {analysis}")
        
        # 构建最终提示
        prompt = f"角色设定：{profile} {background}\n"
        prompt += f"行为准则：{manner}\n"
        prompt += f"对话历史：\n{conversation_str}\n"
        if analysis:
            prompt += f"思考分析：{analysis}\n"
        prompt += f"请以{card.get_assistant_name()}的身份回复用户。"
        
        return prompt, analysis

    async def generate_group_prompt(self, memory, card) -> Tuple[str, str]:
        """
        生成群聊提示
        :param memory: 记忆系统实例
        :param card: 角色卡实例
        :return: 提示和分析结果
        """
        if not hasattr(memory, 'short_term_memory'):
            return "", ""
            
        conversations = memory.short_term_memory
        if not conversations:
            return "", ""
            
        # 获取最近的对话内容
        recent_conversations = conversations[-5:]  # 最近5条消息
        conversation_str = "\n".join([f"{msg['speaker']}: {msg['content']}" for msg in recent_conversations])
        
        # 获取角色信息
        profile = " ".join(card.get_profile())
        background = " ".join(card.get_background())
        manner = " ".join(card.get_rules())
        
        # 构建群聊提示
        prompt = f"角色设定：{profile} {background}\n"
        prompt += f"行为准则：{manner}\n"
        prompt += "你现在在群聊中，需要保持友好、得体的发言风格。\n"
        prompt += "回答要简洁明了，避免过于私人化的内容。\n"
        prompt += "如果有人@你，要礼貌回应；如果是群聊氛围活跃，可以适当参与讨论。\n"
        prompt += f"对话历史：\n{conversation_str}\n"
        prompt += f"请以{card.get_assistant_name()}的身份回复用户。"
        
        return prompt, ""

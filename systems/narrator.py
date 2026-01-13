import logging
import json
from typing import Any

logger = logging.getLogger(__name__)

class Narrator:
    def __init__(self, plugin, launcher_id: str):
        self.plugin = plugin
        self._generator = None
        self._launcher_id = launcher_id
        self._life_data_file = f"life_{launcher_id}"
        self._profile = ""
        self._action = ""
        self._life_data = {}

    def initialize(self):
        """
        初始化旁白系统
        """
        from ..cells.generator import Generator
        self._generator = Generator(self.plugin)

    async def load_config(self):
        """
        加载配置
        """
        await self._load_life_data()

    async def narrate(self, memory, card) -> str:
        """
        生成旁白
        :param memory: 记忆系统实例
        :param card: 角色卡实例
        :return: 旁白内容
        """
        if not hasattr(memory, 'short_term_memory') or not hasattr(memory, 'narrate_max_conversations'):
            return ""
            
        # 获取最近的对话
        conversations = memory.short_term_memory[-memory.narrate_max_conversations:]
        if not conversations:
            return ""
            
        # 简化版的旁白生成
        last_message = conversations[-1]
        last_content = last_message.get('content', '')
        
        # 获取角色信息
        assistant_name = card.get_assistant_name()
        profile = " ".join(card.get_profile() + card.get_background())
        
        # 构建旁白提示
        user_prompt = f"为{assistant_name}生成一个身体动作或场景描述，与刚才的对话自然衔接。"
        user_prompt += f"对话内容：'{last_content}'"
        if profile:
            user_prompt += f" 角色设定：{profile}"
        user_prompt += " 只描写身体动作，不包含对话内容，不超过30个字。"
        
        # 生成旁白
        self._action = await self._generator.generate_response(user_prompt)
        return self._action.strip()

    async def _load_life_data(self):
        """
        加载生活数据
        """
        try:
            data = await self.plugin.get_plugin_storage(self._life_data_file)
            if data:
                self._life_data = json.loads(data.decode("utf-8"))
                logger.info(f"加载生活数据: {self._life_data}")
        except Exception as e:
            logger.error(f"加载生活数据失败: {e}")
            self._life_data = {}

    async def _save_life_data(self):
        """
        保存生活数据
        """
        try:
            data = json.dumps(self._life_data).encode("utf-8")
            await self.plugin.set_plugin_storage(self._life_data_file, data)
            logger.info(f"保存生活数据: {self._life_data}")
        except Exception as e:
            logger.error(f"保存生活数据失败: {e}")

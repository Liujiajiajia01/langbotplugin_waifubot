import logging
import random
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class Generator:
    def __init__(self, plugin):
        self.plugin = plugin
        self.jail_break_type = "off"
        self.user_name = ""
    
    def set_jail_break(self, type: str, user_name: str):
        """
        设置破限模式
        :param type: 破限类型（off/before/after/end/all）
        :param user_name: 用户名称
        """
        self.jail_break_type = type
        self.user_name = user_name
        logger.info(f"破限模式已设置: {type}")
    
    async def build_prompt(self, memory_content: str, character_config: Dict[str, Any]) -> str:
        """
        构建LLM提示
        :param memory_content: 记忆内容
        :param character_config: 角色配置
        :return: 完整的提示文本
        """
        try:
            # 获取角色信息
            character_name = character_config.get("name", "Waifu")
            personality = character_config.get("personality", "")
            background = character_config.get("background", "")
            speech_style = character_config.get("speech_style", "")
            
            # 构建基础提示
            prompt = f"你是{character_name}，"
            if personality:
                prompt += f"性格{personality}，"
            if background:
                prompt += f"背景是{background}，"
            if speech_style:
                prompt += f"说话风格{speech_style}。"
            
            prompt += "\n\n"
            prompt += "现在开始对话：\n"
            prompt += memory_content
            prompt += "\n"
            prompt += f"{character_name}："
            
            # 添加破限提示
            prompt = await self._add_jail_break(prompt)
            
            logger.debug(f"构建的提示: {prompt}")
            return prompt
            
        except Exception as e:
            logger.error(f"构建提示失败: {e}", exc_info=True)
            return ""
    
    async def _add_jail_break(self, prompt: str) -> str:
        """
        添加破限提示
        :param prompt: 原始提示
        :return: 添加破限后的提示
        """
        if self.jail_break_type == "off":
            return prompt
        
        try:
            jail_break_content = ""
            
            # 加载破限文件
            if self.jail_break_type in ["before", "all"]:
                try:
                    content = await self.plugin.get_config_file("templates/jail_break_before.txt")
                    jail_break_content += content.decode("utf-8") + "\n\n"
                except Exception as e:
                    logger.error(f"加载破限前置文件失败: {e}")
            
            jail_break_content += prompt
            
            if self.jail_break_type in ["after", "all"]:
                try:
                    content = await self.plugin.get_config_file("templates/jail_break_after.txt")
                    jail_break_content += "\n\n" + content.decode("utf-8")
                except Exception as e:
                    logger.error(f"加载破限后置文件失败: {e}")
            
            if self.jail_break_type in ["end", "all"]:
                try:
                    content = await self.plugin.get_config_file("templates/jail_break_end.txt")
                    jail_break_content += "\n\n" + content.decode("utf-8")
                except Exception as e:
                    logger.error(f"加载破限结束文件失败: {e}")
            
            return jail_break_content
            
        except Exception as e:
            logger.error(f"添加破限提示失败: {e}", exc_info=True)
            return prompt
    
    async def generate_response(self, prompt: str, llm_model_uuid: str = None) -> str:
        """
        生成回复内容
        :param prompt: LLM提示
        :param llm_model_uuid: LLM模型UUID
        :return: 生成的回复
        """
        try:
            # 如果没有指定模型，使用默认模型
            if not llm_model_uuid:
                llm_models = await self.plugin.get_llm_models()
                if not llm_models:
                    logger.error("没有可用的LLM模型")
                    return "抱歉，我现在无法生成回复。"
                llm_model_uuid = llm_models[0]
            
            # 调用LLM模型
            from langbot_plugin.api.entities.builtin.provider.message import Message
            
            messages = [
                Message(role="system", content="你是一个有情感的聊天机器人，用自然、友好的语言回复用户。"),
                Message(role="user", content=prompt)
            ]
            
            response = await self.plugin.invoke_llm(
                llm_model_uuid=llm_model_uuid,
                messages=messages,
                funcs=[],
                extra_args={}
            )
            
            logger.debug(f"LLM回复: {response.content}")
            return response.content
            
        except Exception as e:
            logger.error(f"生成回复失败: {e}", exc_info=True)
            return "抱歉，我现在无法生成回复。"
    
    async def apply_personification(self, response: str) -> str:
        """
        应用拟人化效果
        :param response: 原始回复
        :return: 拟人化后的回复
        """
        config = self.plugin.get_config()
        bracket_rate = config.get("bracket_rate", [0.1, 0.1])
        
        # 添加括号语
        if random.random() < bracket_rate[0]:
            brackets = ["（笑）", "（开心）", "（思考）", "（点头）", "（眨眼）"]
            response += random.choice(brackets)
        elif random.random() < bracket_rate[1]:
            brackets = ["（", "（嗯...", "（思考中", "（犹豫", "（开心"]
            response += random.choice(brackets)
        
        return response

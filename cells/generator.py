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
            character_profile = character_config.get("Profile", [])
            character_rules = character_config.get("Rules", [])
            
            # 构建完整的提示，包含角色信息和对话历史
            prompt = f"你是{character_name}，"
            
            # 添加角色设定（简洁版）
            if character_profile:
                # 只使用前2条角色设定，避免提示词过长
                profile_text = "，".join(character_profile[:2])
                prompt += f"{profile_text}。"
            
            prompt += "\n\n"
            prompt += "对话历史：\n"
            
            # 添加对话历史，保留完整上下文但限制总长度
            max_memory_length = 1000  # 保留1000字符的历史对话
            if len(memory_content) > max_memory_length:
                # 只保留最近的部分内容
                memory_content = memory_content[-max_memory_length:]
                # 确保从完整的对话行开始
                first_newline = memory_content.find("\n")
                if first_newline != -1:
                    memory_content = memory_content[first_newline+1:]
            
            prompt += memory_content
            prompt += "\n"
            
            # 添加回复规则（简洁版）
            if character_rules:
                # 只使用前3条规则
                rules_text = "\n".join([f"- {rule}" for rule in character_rules[:3]])
                prompt += f"\n回复规则：\n{rules_text}\n"
            
            prompt += f"{character_name}："
            
            # 确保提示词总长度合理
            max_prompt_length = 1500  # 限制在1500字符以内
            if len(prompt) > max_prompt_length:
                # 如果还是过长，优先保留角色设定和最新对话
                prompt = prompt[:max_prompt_length]
                # 确保以角色名称结尾
                if character_name in prompt:
                    prompt = prompt[:prompt.rfind(character_name) + len(character_name) + 1]
                else:
                    prompt += character_name + "："
            
            logger.debug(f"构建的提示: {prompt}")
            logger.debug(f"提示词长度: {len(prompt)} 字符")
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
    
    async def generate_response(self, prompt: str, llm_model_uuid: str = None, ctx=None) -> str:
        """
        生成回复内容
        :param prompt: LLM提示
        :param llm_model_uuid: LLM模型UUID
        :param ctx: 事件上下文
        :return: 生成的回复
        """
        try:
            # 导入正确的Message类
            from langbot_plugin.api.entities.builtin.provider.message import Message
            
            # 确保提示词长度合理
            prompt = prompt[:1500]  # 限制在1500字符以内
            logger.debug(f"最终提示词长度: {len(prompt)} 字符")
            
            # 如果没有指定模型，使用距离当前时间最近的模型
            if not llm_model_uuid:
                llm_models = await self.plugin.get_llm_models()
                logger.debug(f"获取到的LLM模型列表: {llm_models}")
                if not llm_models:
                    logger.error("没有可用的LLM模型")
                    return "抱歉，我现在无法生成回复。"
                
                # 正确处理模型列表，根据返回类型选择模型
                if isinstance(llm_models, list):
                    if llm_models and isinstance(llm_models[0], dict):
                        # 模型列表是字典列表，包含模型详细信息
                        # 选择距离当前时间最近的模型（created_at最大的模型）
                        latest_model = None
                        latest_time = None
                        
                        for model in llm_models:
                            created_at = model.get('created_at', '')
                            if created_at:
                                if not latest_time or created_at > latest_time:
                                    latest_time = created_at
                                    latest_model = model
                        
                        if latest_model:
                            llm_model_uuid = latest_model.get('uuid') or latest_model.get('id')
                            logger.debug(f"使用最新模型: {latest_model.get('name')} (UUID: {llm_model_uuid}, 创建时间: {latest_model.get('created_at')})")
                        else:
                            # 如果没有找到带created_at的模型，退而求其次使用第一个模型
                            model_info = llm_models[0]
                            llm_model_uuid = model_info.get('uuid') or model_info.get('id')
                            logger.debug(f"没有找到带created_at的模型，使用第一个模型: {model_info.get('name')} (UUID: {llm_model_uuid})")
                    else:
                        # 模型列表是UUID字符串列表，无法根据时间选择，使用第一个模型
                        llm_model_uuid = str(llm_models[0])
                        logger.debug(f"模型列表是UUID字符串列表，使用第一个模型UUID: {llm_model_uuid}")
                else:
                    logger.error("获取到的LLM模型列表格式错误")
                    return "抱歉，我现在无法生成回复。"
            
            # 添加回复长度限制的系统提示
            system_content = "你是一个有情感的聊天机器人，用自然、友好的语言回复用户。"
            system_content += "回复要简洁，一般情况下不超过50个汉字。"
            system_content += "只有在非常激动、非常开心，或者非常难受、非常难过的情况下，可以到达100个汉字。"
            
            # 创建完整的Message对象列表，包含系统提示和用户提示
            messages = [
                Message(role="system", content=system_content),
                Message(role="user", content=prompt)
            ]
            
            # 设置合理的超时时间
            extra_args = {
                "timeout": 30  # 设置30秒超时
            }
            
            # 获取API密钥
            api_key = self.plugin.get_config().get("api_key", "")
            
            # 在extra_args中传递API密钥
            if api_key:
                extra_args["api_key"] = api_key
                logger.debug(f"在extra_args中使用API密钥: {api_key[:10]}...{api_key[-10:]}")
            
            # 单次调用，不重试，避免超时累积
            response = await self.plugin.invoke_llm(
                llm_model_uuid=llm_model_uuid,
                messages=messages,
                extra_args=extra_args
            )
            
            logger.debug(f"LLM回复: {response.content}")
            
            # 过滤掉<think>标签内容
            result = response.content
            if '<think>' in result and '</think>' in result:
                result = result.split('</think>')[-1].strip()
            
            # 检查是否有情感分析结果来决定长度限制
            emotion_score = getattr(self.plugin.memories, 'current_emotion_score', 0.0)
            emotion_type = getattr(self.plugin.memories, 'current_emotion_type', 'neutral')
            
            # 默认限制50个汉字，极端情感时限制100个汉字
            max_chars = 50
            if emotion_type in ['positive', 'negative'] and abs(emotion_score) > 0.7:
                max_chars = 100
            
            # 计算汉字数量（假设每个中文汉字占3字节）
            import re
            chinese_chars = re.findall(r'[\u4e00-\u9fa5]', result)
            chinese_count = len(chinese_chars)
            
            # 如果超出限制，截断回复
            if chinese_count > max_chars:
                # 找到第max_chars个汉字的位置
                count = 0
                truncate_pos = 0
                for i, char in enumerate(result):
                    if '\u4e00' <= char <= '\u9fa5':
                        count += 1
                        if count == max_chars:
                            truncate_pos = i + 1
                            break
                
                # 截断并添加省略号
                result = result[:truncate_pos] + "..."
            
            return result
            
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

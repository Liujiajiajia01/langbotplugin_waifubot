import json
import re
import logging
from typing import Dict, Any
import sys
import os

# 添加插件根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))

logger = logging.getLogger(__name__)

class ValueGame:
    def __init__(self, plugin):
        self.plugin = plugin
        self._value = 0
        self._manner_descriptions = []
        self._max_manner_change = 10
        self._value_change = None
        self._config = None
        self._status_file = ""
        self._has_preset = True

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        """
        加载好感度系统配置
        :param character: 角色名称
        :param launcher_id: 启动器ID
        :param launcher_type: 启动器类型
        """
        if character == "off":
            self._has_preset = False
            return
        
        self._has_preset = True

        # 构建状态文件路径
        self._status_file = f"value_game_{character}_{launcher_id}"

        # 加载角色配置
        from cells.config import ConfigManager
        character_config_path = f"config/cards/{character}"
        self._config = ConfigManager(self.plugin)
        await self._config.load_config(character=character, launcher_type=launcher_type, completion=False)

        # 加载当前好感度值
        try:
            value_data = await self.plugin.get_plugin_storage(self._status_file)
            if value_data:
                data = json.loads(value_data.decode("utf-8"))
                self._value = data.get("value", 0)
                logger.info(f"加载好感度值: {self._value}")
            else:
                self._value = 0
                # 如果存储不存在，初始化并保存
                await self._save_value_to_status_file()
        except Exception as e:
            logger.error(f"加载好感度失败: {e}")
            # 出错时初始化好感度
            self._value = 0
            await self._save_value_to_status_file()

        # 获取好感度描述和最大变化值
        self._manner_descriptions = self._config.get("value_descriptions", [])
        self._max_manner_change = self._config.get("max_manner_change", 10)

    async def determine_manner_change(self, memory_content: str, continued_count: int):
        """
        根据对话内容确定好感度变化
        :param memory_content: 记忆内容
        :param continued_count: 继续发言次数
        """
        if not self._has_preset:
            return
        
        # 只处理用户发言
        if "user:" not in memory_content.split("\n")[-1]:
            self._value_change = None
            return
        
        count = continued_count + 1  # 继续发言次数 + 正常回复
        conversations = memory_content.split("\n")[-count:]
        last_content = ""
        
        # 获取最后一条用户消息
        for conv in reversed(conversations):
            if conv.startswith("user:"):
                last_content = conv[5:].strip()
                break
        
        if not last_content:
            self._value_change = None
            return
        
        logger.info(f"分析消息情感: {last_content}")
        
        # 分析情感
        sentiment_result = await self.plugin.text_analyzer.sentiment(text=last_content)
        positive_emotions = sentiment_result.get("positive_num", 0)
        negative_emotions = sentiment_result.get("negative_num", 0)

        # 计算情感分数
        sentiment_score = (positive_emotions - negative_emotions) / (positive_emotions + negative_emotions + 1)
        if sentiment_score == 0:  # 不抵触时默认微量增加
            sentiment_score = 0.1
        
        logger.info(f"情感分析结果: {sentiment_score} {sentiment_result}")

        # 计算好感度变化
        change_amount = int(sentiment_score * self._max_manner_change)

        # 更新好感度
        await self.change_manner_value(change_amount)
        self._value_change = change_amount

    def get_manner_value_str(self) -> str:
        """
        获取好感度字符串表示
        :return: 好感度字符串
        """
        value_change = self._value_change
        
        value_change_str = ""
        if value_change is not None:
            if value_change > 0:
                value_change_str = f"+{value_change}"
            elif value_change < 0:
                value_change_str = f"{value_change}"
            
        content = f"心动值：{self._value}"
        if value_change_str:
            content += f"（{value_change_str}）"
            
        return content

    def get_value(self) -> int:
        """
        获取当前好感度值
        :return: 好感度值
        """
        return self._value

    def get_manner_description(self) -> str:
        """
        获取当前好感度状态描述
        :return: 状态描述
        """
        last_description = ""
        for desc in self._manner_descriptions:
            last_description = self._list_to_prompt_str(desc["description"])
            if self._value <= desc["max"]:
                return last_description
        return last_description

    def _ensure_punctuation(self, text: str) -> str:
        """
        确保文本末尾有标点符号
        :param text: 文本
        :return: 添加标点后的文本
        """
        # 定义中英文标点符号
        punctuation = r"[。.，,？?；;]"
        # 如果末尾没有标点符号，则添加一个句号
        if not re.search(punctuation + r"$", text):
            return text + "。"
        return text

    def _list_to_prompt_str(self, content: list | str, prefix: str = "") -> str:
        """
        将列表转换为提示字符串
        :param content: 内容列表或字符串
        :param prefix: 前缀
        :return: 转换后的字符串
        """
        if isinstance(content, list):
            return "".join([prefix + self._ensure_punctuation(item) for item in content])
        else:
            return self._ensure_punctuation(content)

    async def change_manner_value(self, amount: int):
        """
        改变好感度值
        :param amount: 变化量
        """
        self._value = max(0, min(10000, self._value + amount))
        await self._save_value_to_status_file()
        logger.info(f"好感度已更新: {self._value} (变化: {amount})")

    async def _save_value_to_status_file(self):
        """
        保存好感度值到存储
        """
        try:
            data = json.dumps({"value": self._value}).encode("utf-8")
            await self.plugin.set_plugin_storage(self._status_file, data)
        except Exception as e:
            logger.error(f"保存好感度失败: {e}", exc_info=True)

    async def reset_value(self):
        """
        重置好感度值
        """
        self._value = 0
        await self._save_value_to_status_file()
        logger.info("好感度已重置")

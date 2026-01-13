import yaml
import logging
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ConfigManager:
    def __init__(self, plugin):
        self.plugin = plugin
        self.data = {}
        self.character_config_path = ""
        self.template_path = ""

    async def load_config(self, character: str = "default", launcher_type: str = "person", completion: bool = True):
        """
        加载配置文件
        :param character: 角色卡名称
        :param launcher_type: 启动类型（person/group）
        :param completion: 是否完成配置
        """
        try:
            self.character_config_path = f"config/cards/{character}"
            self.template_path = f"templates/default_{launcher_type}"
            
            # 获取插件配置
            plugin_config = self.plugin.get_config()
            
            # 加载默认模板
            default_config = await self._load_template()
            
            # 加载角色卡配置
            character_config = await self._load_character_config()
            
            # 合并配置
            self.data = {**default_config, **character_config, **plugin_config}
            
            # 如果需要完成配置，进行额外处理
            if completion:
                await self._complete_config()
            
            logger.info(f"配置加载完成: {self.data}")
            return self.data
            
        except Exception as e:
            logger.error(f"加载配置失败: {e}", exc_info=True)
            # 使用默认配置
            self.data = await self._load_template()
            return self.data
    
    async def _load_template(self) -> Dict[str, Any]:
        """
        加载默认模板
        """
        try:
            template_file = f"{self.template_path}.yaml"
            file_bytes = await self.plugin.get_config_file(template_file)
            return yaml.safe_load(file_bytes)
        except Exception as e:
            logger.error(f"加载模板失败: {e}")
            return {}
    
    async def _load_character_config(self) -> Dict[str, Any]:
        """
        加载角色卡配置
        """
        try:
            character_file = f"{self.character_config_path}.yaml"
            file_bytes = await self.plugin.get_config_file(character_file)
            return yaml.safe_load(file_bytes)
        except Exception as e:
            logger.error(f"加载角色卡配置失败: {e}")
            return {}
    
    async def _complete_config(self):
        """
        完成配置，处理默认值和依赖关系
        """
        # 设置默认值
        defaults = {
            "short_term_memory_size": 2000,
            "retrieve_top_n": 3,
            "recall_once": 3,
            "session_memories_size": 6,
            "summary_max_tags": 30,
            "response_min_conversations": 1,
            "response_rate": 1.0,
            "group_response_delay": 0,
            "blacklist": [],
            "repeat_trigger": 2,
            "bracket_rate": [0.1, 0.1],
            "personate_delay": 0,
            "display_value": False,
            "max_narrat_words": 30,
            "narrat_max_conversations": 8,
            "value_game_max_conversations": 5,
            "intervals": [],
            "person_response_delay": 5,
            "continued_rate": 0.0,
            "continued_max_count": 2,
            "proactive_target_user_id": "off",
            "proactive_greeting_enabled": False,
            "proactive_greeting_probability": 50,
            "proactive_min_inactive_hours": 3,
            "proactive_do_not_disturb_start": "23:00",
            "proactive_do_not_disturb_end": "08:00",
            "loop_time": 1800,
            "admin_ids": []
        }
        
        # 合并默认值
        for key, value in defaults.items():
            if key not in self.data:
                self.data[key] = value
    
    def get_config(self) -> Dict[str, Any]:
        """
        获取配置内容
        """
        return self.data
    
    def update_config(self, key: str, value: Any):
        """
        更新配置内容
        """
        self.data[key] = value
        logger.info(f"配置已更新: {key} = {value}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置项，支持默认值
        """
        return self.data.get(key, default)

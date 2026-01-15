import logging
import asyncio
from langbot_plugin.api.definition.plugin import BasePlugin

logger = logging.getLogger(__name__)

class WaifuBotPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.config = None
        self.text_analyzer = None
        self.config_manager = None
        self.generator = None
        self.memories = None
        self.thoughts = None
        self.proactive = None
        self.value_game = None
        self.cards = None
        self.narrator = None
        self.portrait = None
        self.current_bot_uuid = None  # 保存当前机器人的UUID
        self._memory_lock = asyncio.Lock()
        
    async def initialize(self):
        """插件加载时调用"""
        logger.info("WaifuBot插件加载中...")
        
        # 获取插件配置
        self.config = self.get_config()
        safe_config = self.config.copy() if isinstance(self.config, dict) else {}
        if "api_key" in safe_config:
            safe_config["api_key"] = "***"
        logger.info(f"插件配置已加载: keys={list(safe_config.keys())}")
        
        # 初始化各个模块
        try:
            import sys
            import os
            sys.path.append(os.path.dirname(os.path.abspath(__file__)))
            
            from cells.text_analyzer import TextAnalyzer
            from cells.config import ConfigManager
            from cells.generator import Generator
            from cells.cards import Cards
            from organs.memories import Memory
            from organs.thoughts import Thoughts
            from organs.proactive import ProactiveGreeter
            from organs.portrait import UserPortrait
            from systems.value_game import ValueGame
            from systems.narrator import Narrator
            
            self.text_analyzer = TextAnalyzer(self)
            self.config_manager = ConfigManager(self)
            self.generator = Generator(self)
            self.cards = Cards(self)
            self.memories = Memory(self)
            self.thoughts = Thoughts(self)
            self.thoughts.initialize()
            self.value_game = ValueGame(self)
            self.narrator = Narrator(self, "default")
            self.narrator.initialize()
            self.proactive = ProactiveGreeter(self, "default")
            self.proactive.initialize()
            self.portrait = UserPortrait(self)
            
            logger.info("所有模块初始化完成")
        
            # 启动主动交互系统
            await self.proactive.load_config(self.memories)
            await self.proactive.start()
            
            logger.info("WaifuBot插件加载完成！")
            
        except Exception as e:
            logger.error(f"模块初始化失败: {e}", exc_info=True)
            raise
    
    def __del__(self):
        """插件卸载时调用"""
        logger.info("WaifuBot插件卸载中...")
        
        # 注意：__del__方法不能调用异步方法，数据已在正常操作中保存
        logger.info("数据保存已在正常操作中完成")
        
        logger.info("WaifuBot插件卸载完成！")

# 创建插件实例
bot = WaifuBotPlugin()

# 导出插件实例，必须使用此变量名
plugin = bot

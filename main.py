import logging
from langbot_plugin.api import BasePlugin

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
        
    async def on_load(self):
        """插件加载时调用"""
        logger.info("WaifuBot插件加载中...")
        
        # 获取插件配置
        self.config = self.get_config()
        logger.info(f"插件配置: {self.config}")
        
        # 初始化各个模块
        try:
            from .cells.text_analyzer import TextAnalyzer
            from .cells.config import ConfigManager
            from .cells.generator import Generator
            from .cells.cards import Cards
            from .organs.memories import Memory
            from .organs.thoughts import Thoughts
            from .organs.proactive import ProactiveGreeter
            from .organs.portrait import UserPortrait
            from .systems.value_game import ValueGame
            from .systems.narrator import Narrator
            
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
            
        except Exception as e:
            logger.error(f"模块初始化失败: {e}", exc_info=True)
            raise
        
        logger.info("WaifuBot插件加载完成！")
    
    async def on_unload(self):
        """插件卸载时调用"""
        logger.info("WaifuBot插件卸载中...")
        
        # 停止主动交互系统
        try:
            await self.proactive.stop()
            logger.info("主动交互系统已停止")
        except Exception as e:
            logger.error(f"停止主动交互系统失败: {e}", exc_info=True)
        
        # 保存数据
        try:
            if hasattr(self.memories, 'save_long_term_memories'):
                await self.memories.save_long_term_memories()
            if hasattr(self.value_game, '_save_value_to_status_file'):
                self.value_game._save_value_to_status_file()
            logger.info("数据保存完成")
        except Exception as e:
            logger.error(f"数据保存失败: {e}", exc_info=True)
        
        logger.info("WaifuBot插件卸载完成！")

# 创建插件实例
bot = WaifuBotPlugin()

# 导出插件实例，必须使用此变量名
plugin = bot

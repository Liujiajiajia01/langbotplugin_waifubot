import logging
import asyncio
import datetime
import json
from typing import Optional, Any

logger = logging.getLogger(__name__)

class ProactiveGreeter:
    def __init__(self, plugin, launcher_id: str):
        self.plugin = plugin
        self._generator = None
        self._main_task: Optional[asyncio.Task] = None
        self._launcher_id = launcher_id
        self._memory = None
        
        # 配置参数
        self._proactive_target_user_id = "off"
        self._proactive_greeting_enabled = False
        self._proactive_greeting_probability = 0
        self._proactive_min_inactive_hours = 3.0
        self._proactive_max_inactive_hours = 4.0
        self._proactive_do_not_disturb_start = "23:00"
        self._proactive_do_not_disturb_end = "08:00"
        self._loop_time = 1800

    def initialize(self):
        """
        初始化主动交互系统
        """
        from ..cells.generator import Generator
        self._generator = Generator(self.plugin)

    async def load_config(self, memory, summary_mode: bool = False):
        """
        加载配置
        :param memory: 记忆系统实例
        :param summary_mode: 是否开启摘要模式
        """
        self._memory = memory
        
        # 获取插件配置
        config = self.plugin.get_config()
        self._proactive_target_user_id = config.get("proactive_target_user_id", "off")
        self._proactive_greeting_enabled = config.get("proactive_greeting_enabled", False)
        self._proactive_greeting_probability = config.get("proactive_greeting_probability", 0)
        self._proactive_min_inactive_hours = config.get("proactive_min_inactive_hours", 3.0)
        self._proactive_max_inactive_hours = config.get("proactive_max_inactive_hours", 4.0)
        
        if self._proactive_max_inactive_hours < self._proactive_min_inactive_hours:
            self._proactive_max_inactive_hours = self._proactive_min_inactive_hours
            
        self._proactive_do_not_disturb_start = config.get("proactive_do_not_disturb_start", "23:00")
        self._proactive_do_not_disturb_end = config.get("proactive_do_not_disturb_end", "08:00")
        self._loop_time = config.get("loop_time", 1800)
        
        logger.info(f"主动交互系统配置加载完成: {config}")

    async def start(self):
        """
        启动主动交互循环
        """
        if not self._proactive_greeting_enabled:
            logger.info("主动交互功能未启用")
            return
            
        if self._main_task is not None and not self._main_task.done():
            logger.info("主动交互循环已经在运行")
            return
            
        logger.info("启动主动交互循环")
        self._main_task = asyncio.create_task(self._proactive_loop())

    async def stop(self):
        """
        停止主动交互循环
        """
        if self._main_task is not None and not self._main_task.done():
            logger.info("停止主动交互循环")
            self._main_task.cancel()
            try:
                await self._main_task
            except asyncio.CancelledError:
                pass
            self._main_task = None

    async def _proactive_loop(self):
        """
        主动交互循环
        """
        while True:
            try:
                await asyncio.sleep(self._loop_time)
                
                # 检查是否应该发送主动消息
                if await self._should_send_proactive_message():
                    await self._send_proactive_message()
                    
            except asyncio.CancelledError:
                logger.info("主动交互循环被取消")
                break
            except Exception as e:
                logger.error(f"主动交互循环出错: {e}", exc_info=True)
                await asyncio.sleep(self._loop_time)

    async def _should_send_proactive_message(self) -> bool:
        """
        判断是否应该发送主动消息
        :return: 是否应该发送
        """
        # 检查是否启用
        if not self._proactive_greeting_enabled:
            return False
            
        # 检查目标用户ID
        if self._proactive_target_user_id == "off":
            return False
            
        # 检查勿扰时间
        if not self._is_in_allowed_time_window():
            return False
            
        # 检查不活跃时间
        if not await self._check_inactivity_time():
            return False
            
        # 检查概率
        import random
        if random.randint(1, 100) > self._proactive_greeting_probability:
            return False
            
        return True

    def _is_in_allowed_time_window(self) -> bool:
        """
        检查是否在允许的时间窗口内
        :return: 是否在允许的时间窗口内
        """
        now = datetime.datetime.now().time()
        
        # 解析勿扰时间
        start_hour, start_minute = map(int, self._proactive_do_not_disturb_start.split(":"))
        end_hour, end_minute = map(int, self._proactive_do_not_disturb_end.split(":"))
        
        start_time = datetime.time(start_hour, start_minute)
        end_time = datetime.time(end_hour, end_minute)
        
        # 判断当前时间是否在勿扰时间段内
        if start_time < end_time:
            # 勿扰时间在同一天内
            return not (start_time <= now <= end_time)
        else:
            # 勿扰时间跨天
            return not (now >= start_time or now <= end_time)

    async def _check_inactivity_time(self) -> bool:
        """
        检查用户不活跃时间
        :return: 是否达到不活跃时间阈值
        """
        if not self._memory or not hasattr(self._memory, 'short_term_memory'):
            return False
            
        # 获取最后一次互动时间
        if not self._memory.short_term_memory:
            return False
            
        last_message = self._memory.short_term_memory[-1]
        last_time = last_message.get('timestamp', 0)
        
        # 计算不活跃时间（小时）
        inactive_hours = (datetime.datetime.now().timestamp() - last_time) / 3600
        
        return self._proactive_min_inactive_hours <= inactive_hours <= self._proactive_max_inactive_hours

    async def _send_proactive_message(self):
        """
        发送主动消息
        """
        try:
            # 获取目标用户和机器人信息
            bot_uuid = ""
            bots = await self.plugin.get_bots()
            if bots:
                bot_uuid = bots[0]
            
            if not bot_uuid:
                logger.error("找不到可用的机器人")
                return
                
            # 生成主动消息内容
            message_content = await self._generate_proactive_message()
            if not message_content:
                logger.error("生成主动消息失败")
                return
                
            # 发送消息
            from langbot_plugin.api.entities.builtin.platform.message import MessageChain, Plain
            
            await self.plugin.send_message(
                bot_uuid=bot_uuid,
                target_type="person",
                target_id=self._proactive_target_user_id,
                message_chain=MessageChain([Plain(text=message_content)])
            )
            
            logger.info(f"发送主动消息给用户 {self._proactive_target_user_id}: {message_content}")
            
        except Exception as e:
            logger.error(f"发送主动消息失败: {e}", exc_info=True)

    async def _generate_proactive_message(self) -> str:
        """
        生成主动消息内容
        :return: 消息内容
        """
        # 构建生成提示
        prompt = "生成一条友好的主动问候消息，用于开启对话。消息要自然、亲切，不超过50个字。"
        
        # 调用生成器生成消息
        message = await self._generator.generate_response(prompt)
        return message.strip()

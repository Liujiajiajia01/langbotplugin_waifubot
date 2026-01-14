import logging
import asyncio
import datetime
import json
from typing import Optional, Any
import sys
import os

# 添加插件根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))))

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
        self._proactive_min_inactive_minutes = 180.0  # 最小不活跃时间（分钟）
        self._proactive_do_not_disturb_start = "23:00"
        self._proactive_do_not_disturb_end = "08:00"
        self._loop_time = 60  # 检查间隔（秒）

    def initialize(self):
        """
        初始化主动交互系统
        """
        from cells.generator import Generator
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
        
        # 兼容旧配置
        if "proactive_min_inactive_minutes" in config:
            self._proactive_min_inactive_minutes = config.get("proactive_min_inactive_minutes", 180.0)
        else:
            # 旧配置单位是小时，转换为分钟
            self._proactive_min_inactive_minutes = config.get("proactive_min_inactive_hours", 3.0) * 60
            
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
                logger.info("主动交互循环检查开始")
                await asyncio.sleep(self._loop_time)
                
                # 检查是否应该发送主动消息
                if await self._should_send_proactive_message():
                    logger.info("满足所有主动消息发送条件")
                    await self._send_proactive_message()
                else:
                    logger.info("不满足主动消息发送条件")
                    
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
            logger.info("主动消息功能未启用")
            return False
            
        logger.info(f"主动消息功能已启用，概率: {self._proactive_greeting_probability}%")
        
        # 检查目标用户ID
        if self._proactive_target_user_id == "off":
            logger.info("目标用户ID未设置")
            return False
            
        logger.info(f"目标用户ID: {self._proactive_target_user_id}")
        
        # 检查勿扰时间
        if not self._is_in_allowed_time_window():
            logger.info("当前处于勿扰时间段内")
            return False
            
        logger.info("当前处于允许发送主动消息的时间段内")
        
        # 检查不活跃时间
        if not await self._check_inactivity_time():
            return False
            
        logger.info("用户不活跃时间达到阈值")
        
        # 检查概率
        import random
        random_num = random.randint(1, 100)
        if random_num > self._proactive_greeting_probability:
            logger.info(f"概率检查不通过 (随机数: {random_num}, 阈值: {self._proactive_greeting_probability})")
            return False
            
        logger.info(f"概率检查通过 (随机数: {random_num}, 阈值: {self._proactive_greeting_probability})")
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
        if not self._memory:
            logger.info("记忆系统未初始化")
            return False
            
        if not hasattr(self._memory, 'short_term_memory'):
            logger.info("记忆系统缺少short_term_memory属性")
            return False
            
        # 获取最后一次互动时间
        if not self._memory.short_term_memory:
            logger.info("短期记忆为空")
            return False
            
        last_message = self._memory.short_term_memory[-1]
        last_time = last_message.get('timestamp', 0)
        
        logger.info(f"最后一条消息时间戳: {last_time}, 当前时间戳: {datetime.datetime.now().timestamp()}")
        
        # 计算不活跃时间
        inactive_seconds = datetime.datetime.now().timestamp() - last_time
        inactive_minutes = inactive_seconds / 60
        
        logger.info(f"用户不活跃时间: {inactive_seconds:.2f} 秒 ({inactive_minutes:.2f} 分钟), 最小阈值: {self._proactive_min_inactive_minutes} 分钟")
        
        # 只检查是否大于等于最小阈值
        return inactive_minutes >= self._proactive_min_inactive_minutes

    async def _send_proactive_message(self):
        """
        发送主动消息
        """
        try:
            # 获取目标用户和机器人信息
            bot_uuid = ""
            
            # 优先使用之前保存的当前机器人UUID
            if hasattr(self.plugin, 'current_bot_uuid') and self.plugin.current_bot_uuid:
                bot_uuid = self.plugin.current_bot_uuid
                logger.info(f"使用保存的当前机器人UUID: {bot_uuid}")
                
                # 验证机器人UUID是否在机器人列表中
                try:
                    bots = await self.plugin.get_bots()
                    logger.info(f"验证机器人列表: {bots}")
                    bot_exists = False
                    if bots and isinstance(bots, list):
                        for bot in bots:
                            if isinstance(bot, dict):
                                if bot.get('uuid') == bot_uuid:
                                    bot_exists = True
                                    logger.info(f"机器人UUID {bot_uuid} 存在于机器人列表中")
                                    break
                            elif isinstance(bot, str):
                                if bot == bot_uuid:
                                    bot_exists = True
                                    logger.info(f"机器人UUID {bot_uuid} 存在于机器人列表中")
                                    break
                    
                    if not bot_exists:
                        logger.warning(f"机器人UUID {bot_uuid} 不存在于机器人列表中，将尝试使用机器人列表中的第一个机器人")
                        bot_uuid = ""
                except Exception as e:
                    logger.error(f"验证机器人UUID时出错: {e}")
            
            if not bot_uuid:
                # 如果没有保存的UUID或保存的UUID无效，则获取机器人列表
                bots = await self.plugin.get_bots()
                logger.info(f"获取到的机器人列表: {bots}")
                
                if bots and isinstance(bots, list) and len(bots) > 0:
                    if isinstance(bots[0], dict):
                        # 如果是字典，提取uuid字段
                        bot_uuid = bots[0].get('uuid', '')
                        logger.info(f"从字典获取bot_uuid: {bot_uuid}")
                    elif isinstance(bots[0], str):
                        # 如果是字符串，直接使用
                        bot_uuid = bots[0]
                        logger.info(f"直接获取bot_uuid: {bot_uuid}")
                    else:
                        logger.error(f"未知的bot类型: {type(bots[0])}, 内容: {bots[0]}")
                else:
                    logger.error("无法获取有效的机器人列表")
            
            if not bot_uuid:
                logger.error("找不到可用的机器人UUID")
                return
                
            # 生成主动消息内容
            message_content = await self._generate_proactive_message()
            if not message_content:
                logger.error("生成主动消息失败")
                return
                
            # 发送消息
                from langbot_plugin.api.entities.builtin.platform.message import MessageChain, Plain
                
                # 确保用户ID是字符串格式
                target_id = str(self._proactive_target_user_id)
                
                # 简化消息内容，去掉表情符号，使用纯文本格式
                # 这有助于解决某些平台对特殊字符的限制问题
                import re
                simple_message = re.sub(r'[\u2600-\u27BF\u3000-\u303F\uFE00-\uFE0F\uF0000-\uF0FFF]', '', message_content)
                logger.info(f"简化后的消息内容: {simple_message}")
                
                logger.info(f"准备发送消息: bot_uuid={bot_uuid}, target_type='person', target_id={target_id}, 目标用户ID类型: {type(self._proactive_target_user_id)}")
                
                try:
                    # 先记录更多的调试信息
                    logger.info("开始调用send_message方法")
                    
                    # 尝试使用简化的消息内容发送
                    await self.plugin.send_message(
                        bot_uuid=bot_uuid,
                        target_type="person",
                        target_id=target_id,
                        message_chain=MessageChain([Plain(text=simple_message)])
                    )
                    
                    logger.info("send_message方法调用成功")
                    
                except Exception as send_error:
                    logger.error(f"send_message方法调用失败: {send_error}", exc_info=True)
                    raise
            
            logger.info(f"发送主动消息给用户 {self._proactive_target_user_id}: {message_content}")
            
        except Exception as e:
            logger.error(f"发送主动消息失败: {e}", exc_info=True)

    async def _generate_proactive_message(self) -> str:
        """
        生成主动消息内容
        :return: 消息内容
        """
        # 构建生成提示，要求使用简单格式，避免特殊字符
        prompt = "生成一条友好的主动问候消息，用于开启对话。消息要自然、亲切，不超过50个字，不要使用表情符号或特殊格式，使用纯文本即可。"
        
        # 调用生成器生成消息
        message = await self._generator.generate_response(prompt)
        return message.strip()

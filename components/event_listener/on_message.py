import logging
from langbot_plugin.api import EventListener, EventContext
from langbot_plugin.api.entities.builtin.platform.message import Plain, MessageChain
from langbot_plugin.api.entities.builtin.platform.event import FriendMessageReceived, GroupMessageReceived

logger = logging.getLogger(__name__)

class OnMessageEventListener(EventListener):
    def __init__(self, plugin):
        super().__init__(plugin)
        self.group_blacklist = set()
        self.repeat_messages = {}
        
    async def on_friend_message_received(self, ctx: EventContext):
        """处理私信消息"""
        try:
            logger.info("收到私信消息")
            
            # 获取消息内容
            message_chain = ctx.query.message_chain
            text = "".join([elem.text for elem in message_chain if hasattr(elem, 'text')])
            
            if not text:
                logger.debug("消息内容为空，忽略")
                return
            
            # 获取用户信息
            user_id = str(ctx.query.sender.user_id)
            user_name = ctx.query.sender.nickname or f"用户{user_id}"
            
            # 初始化记忆系统
            if not hasattr(self.plugin.memories, 'user_id') or self.plugin.memories.user_id != user_id:
                await self.plugin.memories.initialize(user_name, "Waifu", user_id)
            
            # 加载角色卡
            character = self.plugin.get_config().get("character", "default")
            await self.plugin.cards.load_config(character, "person")
            
            # 加载好感度系统配置
            await self.plugin.value_game.load_config(
                character=character,
                launcher_id=user_id,
                launcher_type="person"
            )
            
            # 分析用户消息，更新画像
            if hasattr(self.plugin, 'portrait'):
                await self.plugin.portrait.analyze_user_message(user_id, text)
            
            # 添加短期记忆
            await self.plugin.memories.add_short_term_memory("user", text)
            
            # 更新会话记忆池
            await self.plugin.memories.update_session_memories(text)
            
            # 确定好感度变化
            await self.plugin.value_game.determine_manner_change(
                self.plugin.memories.get_short_term_memory_text(),
                continued_count=0
            )
            
            # 生成思维分析
            prompt, analysis = await self.plugin.thoughts.generate_person_prompt(
                self.plugin.memories, self.plugin.cards
            )
            
            # 如果开启了思维显示，添加到回复中
            if self.plugin.get_config().get("display_thinking", False) and analysis:
                response_content = f"（思考：{analysis}）\n"
            else:
                response_content = ""
            
            # 生成回复
            response = await self.plugin.generator.generate_response(prompt)
            response_content += response
            
            # 应用拟人化效果
            response_content = await self.plugin.generator.apply_personification(response_content)
            
            # 添加好感度显示（如果启用）
            if self.plugin.get_config().get("display_value", False):
                response_content += " " + self.plugin.value_game.get_manner_value_str()
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text=response_content)
                ])
            )
            
            # 添加机器人回复到短期记忆
            await self.plugin.memories.add_short_term_memory("bot", response_content)
            
            # 如果开启了剧情模式，生成旁白
            if self.plugin.get_config().get("story_mode", False):
                narration = await self.plugin.narrator.narrate(
                    self.plugin.memories, self.plugin.cards
                )
                if narration:
                    await ctx.reply(
                        MessageChain([
                            Plain(text=narration)
                        ])
                    )
                    await self.plugin.memories.add_short_term_memory("narrator", narration)
            
            # 如果开启了长期记忆，定期总结
            if self.plugin.get_config().get("summarization_mode", True):
                await self.plugin.memories.summarize_long_term_memory()
            
            logger.info(f"私信回复用户 {user_name}: {response_content}")
            
        except Exception as e:
            logger.error(f"处理私信消息失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([
                    Plain(text="抱歉，我现在无法回复你的消息。")
                ])
            )
    
    async def on_group_message_received(self, ctx: EventContext):
        """处理群聊消息"""
        try:
            logger.info("收到群聊消息")
            
            # 获取群聊信息
            group_id = str(ctx.query.group_id)
            
            # 检查群聊是否在黑名单中
            if group_id in self.group_blacklist:
                logger.debug(f"群聊 {group_id} 在黑名单中，忽略消息")
                return
            
            # 获取消息内容
            message_chain = ctx.query.message_chain
            text = "".join([elem.text for elem in message_chain if hasattr(elem, 'text')])
            
            if not text:
                logger.debug("消息内容为空，忽略")
                return
            
            # 获取用户信息
            user_id = str(ctx.query.sender.user_id)
            user_name = ctx.query.sender.nickname or f"用户{user_id}"
            
            # 加载角色卡（群聊版本）
            character = self.plugin.get_config().get("character", "default")
            await self.plugin.cards.load_config(character, "group")
            
            # 群聊复读功能
            repeat_threshold = self.plugin.get_config().get("group_repeat_threshold", 3)
            if await self._check_repeat(group_id, text, repeat_threshold):
                await ctx.reply(
                    MessageChain([
                        Plain(text=text)
                    ])
                )
                logger.info(f"群聊 {group_id} 复读: {text}")
                return
            
            # 检查是否@机器人
            is_at_me = any(hasattr(elem, 'target') and elem.target == self.plugin.get_bot_info().user_id for elem in message_chain)
            
            # 群聊模式下，只回复@自己的消息或关键词触发
            if not is_at_me:
                # 检查是否包含触发关键词
                trigger_keywords = self.plugin.get_config().get("group_trigger_keywords", [])
                if not any(keyword in text for keyword in trigger_keywords):
                    logger.debug(f"群聊消息未@机器人且无触发关键词，忽略: {text}")
                    return
            
            # 初始化记忆系统（群聊专用）
            if not hasattr(self.plugin.memories, 'user_id') or self.plugin.memories.user_id != f"group_{group_id}_{user_id}":
                await self.plugin.memories.initialize(user_name, "Waifu", f"group_{group_id}_{user_id}")
            
            # 加载好感度系统配置
            await self.plugin.value_game.load_config(
                character=character,
                launcher_id=user_id,
                launcher_type="group"
            )
            
            # 添加短期记忆
            await self.plugin.memories.add_short_term_memory("user", f"[{user_name}] {text}")
            
            # 更新会话记忆池
            await self.plugin.memories.update_session_memories(f"[{user_name}] {text}")
            
            # 确定好感度变化
            await self.plugin.value_game.determine_manner_change(
                self.plugin.memories.get_short_term_memory_text(),
                continued_count=0
            )
            
            # 生成思维分析
            prompt, analysis = await self.plugin.thoughts.generate_group_prompt(
                self.plugin.memories, self.plugin.cards
            )
            
            # 生成回复
            response = await self.plugin.generator.generate_response(prompt)
            
            # 应用拟人化效果（群聊版本，更公开得体）
            response = await self.plugin.generator.apply_personification(response, mode="group")
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text=response)
                ])
            )
            
            # 添加机器人回复到短期记忆
            await self.plugin.memories.add_short_term_memory("bot", response)
            
            logger.info(f"群聊 {group_id} 回复用户 {user_name}: {response}")
            
        except Exception as e:
            logger.error(f"处理群聊消息失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([
                    Plain(text="抱歉，我现在无法回复消息。")
                ])
            )
    
    async def _check_repeat(self, group_id: str, text: str, threshold: int) -> bool:
        """检查群聊消息是否需要复读"""
        if group_id not in self.repeat_messages:
            self.repeat_messages[group_id] = {}
        
        # 更新消息计数
        self.repeat_messages[group_id][text] = self.repeat_messages[group_id].get(text, 0) + 1
        
        # 如果达到阈值，重置计数并返回True
        if self.repeat_messages[group_id][text] >= threshold:
            self.repeat_messages[group_id][text] = 0
            return True
        
        return False
    
    async def add_to_blacklist(self, group_id: str):
        """将群聊添加到黑名单"""
        self.group_blacklist.add(group_id)
        logger.info(f"群聊 {group_id} 已添加到黑名单")
    
    async def remove_from_blacklist(self, group_id: str):
        """将群聊从黑名单移除"""
        if group_id in self.group_blacklist:
            self.group_blacklist.remove(group_id)
            logger.info(f"群聊 {group_id} 已从黑名单移除")

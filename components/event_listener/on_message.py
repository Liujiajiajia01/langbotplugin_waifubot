import logging
from langbot_plugin.api.definition.components.common.event_listener import EventListener
from langbot_plugin.api.entities import events, context
from langbot_plugin.api.entities.builtin.platform.message import Plain, MessageChain

logger = logging.getLogger(__name__)

class OnMessageEventListener(EventListener):
    def __init__(self):
        super().__init__()
        self.group_blacklist = set()
        self.repeat_messages = {}
        
        @self.handler(events.PersonNormalMessageReceived)
        async def on_person_message_received(ctx: context.EventContext):
            """处理私信消息"""
            try:
                logger.info("收到私信消息")
                
                # 获取当前机器人的UUID
                bot_uuid = await ctx.get_bot_uuid()
                logger.info(f"当前机器人UUID: {bot_uuid}")
                # 将UUID保存到插件实例中
                self.plugin.current_bot_uuid = bot_uuid

                # 获取消息内容
                message_chain = ctx.event.message_chain
                text = "".join([elem.text for elem in message_chain if hasattr(elem, 'text')])

                if not text:
                    logger.debug("消息内容为空，忽略")
                    return

                # 获取用户信息
                user_id = str(ctx.event.sender_id)
                # 用户名称可能需要通过其他方式获取，暂时使用用户ID作为名称
                user_name = f"用户{user_id}"

                # 获取插件实例
                plugin = self.plugin

                # 初始化记忆系统
                if not hasattr(plugin.memories, 'user_id') or plugin.memories.user_id != user_id:
                    await plugin.memories.initialize(user_name, "Waifu", user_id)

                # 加载角色卡（支持按用户ID配置）
                # 获取默认角色卡
                default_character = plugin.get_config().get("character", "cute_neko")
                
                # 获取用户角色映射
                user_character_mappings = plugin.get_config().get("user_character_mappings", {})
                
                # 确保用户角色映射是字典类型
                if not isinstance(user_character_mappings, dict):
                    # 尝试将字符串解析为JSON字典
                    try:
                        import json
                        user_character_mappings = json.loads(user_character_mappings)
                        logger.info(f"成功将user_character_mappings字符串解析为字典: {user_character_mappings}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"user_character_mappings 不是字典类型且解析失败，使用默认角色卡: {default_character}, 错误: {e}")
                        character = default_character
                        user_character_mappings = {}
                
                # 根据用户ID选择角色卡
                if isinstance(user_character_mappings, dict):
                    character = user_character_mappings.get(user_id, default_character)
                else:
                    character = default_character
                
                logger.info(f"用户 {user_id} 使用角色卡: {character}")
                await plugin.cards.load_config(character, "person")

                # 添加短期记忆
                await plugin.memories.add_short_term_memory("user", text)

                # 生成思维分析
                prompt, analysis = await plugin.thoughts.generate_person_prompt(
                    plugin.memories, plugin.cards
                )

                # 生成回复，传递事件上下文以使用流水线配置的模型
                response = await plugin.generator.generate_response(prompt, ctx=ctx)

                # 应用拟人化效果
                response = await plugin.generator.apply_personification(response)

                # 实现打字机效果，分段发送消息
                await self.send_with_typing_effect(ctx, response)

                # 添加机器人回复到短期记忆
                response_content = response.split("\n")[0]  # 只保存第一行作为记忆
                await plugin.memories.add_short_term_memory("bot", response_content)



                # 如果开启了好感度显示，显示当前好感度
                if plugin.get_config().get("display_value", False):
                    from systems.value_game import ValueGame
                    # 初始化好感度系统
                    value_game = ValueGame(plugin)
                    await value_game.load_config(character, user_id, "person")
                    # 计算好感度变化
                    memory_content = plugin.memories.get_short_term_memory_text()
                    await value_game.determine_manner_change(memory_content, 0)
                    # 显示好感度
                    value_text = value_game.get_manner_value_str()
                    if value_text:
                        await ctx.reply(
                            MessageChain([
                                Plain(text=value_text)
                            ])
                        )
                    # 即使没有变化也显示当前好感度
                    elif plugin.get_config().get("display_value_always", False):
                        await ctx.reply(
                            MessageChain([
                                Plain(text=f"心动值：{value_game.get_value()}")
                            ])
                        )

                # 记忆总结不再由消息触发，而是由短期记忆大小阈值自动触发
                # 这样可以避免每次消息都调用LLM，减少超时风险
                # if plugin.get_config().get("summarization_mode", True):
                #     await plugin.memories.summarize_long_term_memory()

                # 阻止默认的流水线处理流程，避免重复回复
                ctx.prevent_default()

                logger.info(f"私信回复用户 {user_name}: {response_content}")

            except Exception as e:
                logger.error(f"处理私信消息失败: {e}", exc_info=True)
                await ctx.reply(
                    MessageChain([
                        Plain(text="抱歉，我现在无法回复你的消息。")
                    ])
                )

    async def send_with_typing_effect(self, ctx, message: str, delay: float = 0.05):
        """
        实现打字机效果，分段发送消息
        :param ctx: 事件上下文
        :param message: 要发送的消息
        :param delay: 每个字符的延迟时间（秒）
        """
        import asyncio
        import re
        
        # 将消息按句号、叹号、问号、分号、冒号、换行分段，逗号不分段
        segments = re.split(r'([。！？；：\n])', message)
        
        # 重组段落，确保标点符号和内容在一起
        combined_segments = []
        i = 0
        while i < len(segments):
            if i + 1 < len(segments):
                # 将内容和标点符号合并
                combined_segments.append(segments[i] + segments[i+1])
                i += 2
            else:
                # 处理最后一个单独的内容片段
                combined_segments.append(segments[i])
                i += 1
        
        # 过滤掉空段落
        combined_segments = [seg for seg in combined_segments if seg.strip()]
        
        # 逐个发送段落，每次只发送当前片段
        for segment in combined_segments:
            if segment.strip():
                # 等待一段时间模拟打字效果
                await asyncio.sleep(delay * len(segment))
                # 只发送当前片段
                await ctx.reply(
                    MessageChain([
                        Plain(text=segment)
                    ])
                )

        @self.handler(events.GroupNormalMessageReceived)
        async def on_group_message_received(ctx: context.EventContext):
            """处理群聊消息"""
            try:
                logger.info("收到群聊消息")
                
                # 获取当前机器人的UUID
                bot_uuid = await ctx.get_bot_uuid()
                logger.info(f"当前机器人UUID: {bot_uuid}")
                # 将UUID保存到插件实例中
                self.plugin.current_bot_uuid = bot_uuid
                
                # 调试：打印事件对象的所有属性
                logger.info(f"群聊事件对象: {ctx.event}")
                logger.info(f"群聊事件对象属性: {dir(ctx.event)}")
                
                # 获取群聊信息，尝试不同的属性名称
                group_id = None
                user_id = str(ctx.event.sender_id)
                
                # 尝试获取群聊ID
                if hasattr(ctx.event, 'group_id'):
                    group_id = str(ctx.event.group_id)
                    logger.info(f"使用group_id: {group_id}")
                elif hasattr(ctx.event, 'target_id'):
                    group_id = str(ctx.event.target_id)
                    logger.info(f"使用target_id作为group_id: {group_id}")
                elif hasattr(ctx.event, 'channel_id'):
                    group_id = str(ctx.event.channel_id)
                    logger.info(f"使用channel_id作为group_id: {group_id}")
                else:
                    # 如果都没有，尝试从事件对象中提取
                    logger.error("无法找到群聊ID属性")
                    # 尝试作为临时解决方案，使用一个默认值
                    group_id = "default_group"
                # 用户名称可能需要通过其他方式获取，暂时使用用户ID作为名称
                user_name = f"用户{user_id}"

                # 获取消息内容
                message_chain = ctx.event.message_chain
                text = "".join([elem.text for elem in message_chain if hasattr(elem, 'text')])

                if not text:
                    logger.debug("群聊消息内容为空，忽略")
                    return

                # 检查是否在黑名单中
                if group_id in self.group_blacklist:
                    logger.debug(f"群聊 {group_id} 在黑名单中，忽略消息")
                    return

                # 获取插件实例
                plugin = self.plugin

                # 忽略特定前缀的消息
                ignore_prefixes = plugin.get_config().get("ignore_prefix", ["/"])  # 默认忽略以/开头的消息
                if any(text.startswith(prefix) for prefix in ignore_prefixes):
                    logger.debug(f"群聊消息以忽略前缀开头，忽略消息: {text}")
                    return

                logger.info(f"群聊 {group_id} 将处理用户 {user_name} 的消息: {text}")

                # 初始化记忆系统（群聊专用）
                logger.info(f"初始化群聊 {group_id} 用户 {user_id} 的记忆系统")
                if not hasattr(plugin.memories, 'user_id') or plugin.memories.user_id != f"group_{group_id}_{user_id}":
                    await plugin.memories.initialize(user_name, "Waifu", f"group_{group_id}_{user_id}")
                    logger.info(f"记忆系统初始化完成，当前用户ID: {plugin.memories.user_id}")

                # 加载角色卡（群聊版本，更公开得体）
                character = plugin.get_config().get("group_character", "cute_neko")
                logger.info(f"群聊将加载角色卡: {character}")
                await plugin.cards.load_config(character, "group")
                logger.info(f"群聊角色卡加载完成，角色信息：profile={plugin.cards.get_profile(mode='group')}, background={plugin.cards.get_background(mode='group')}, rules={plugin.cards.get_rules(mode='group')}")
                logger.info(f"角色卡配置: 用户名称={plugin.cards.get_user_name()}, 助手名称={plugin.cards.get_assistant_name()}")

                # 添加用户消息到短期记忆
                await plugin.memories.add_short_term_memory(user_name, text)

                # 生成思维分析
                prompt, analysis = await plugin.thoughts.generate_group_prompt(
                    plugin.memories, plugin.cards
                )

                # 生成回复
                response = await plugin.generator.generate_response(prompt)

                # 应用拟人化效果（群聊版本，更公开得体）
                response = await plugin.generator.apply_personification(response, mode="group")

                # 实现打字机效果，分段发送消息
                await self.send_with_typing_effect(ctx, response)

                # 添加机器人回复到短期记忆
                await plugin.memories.add_short_term_memory("bot", response)

                # 如果开启了好感度显示，显示当前好感度
                if plugin.get_config().get("display_value", False):
                    from systems.value_game import ValueGame
                    # 初始化好感度系统
                    value_game = ValueGame(plugin)
                    await value_game.load_config(character, f"group_{group_id}_{user_id}", "group")
                    # 计算好感度变化
                    memory_content = plugin.memories.get_short_term_memory_text()
                    await value_game.determine_manner_change(memory_content, 0)
                    # 显示好感度
                    value_text = value_game.get_manner_value_str()
                    if value_text:
                        await ctx.reply(
                            MessageChain([
                                Plain(text=value_text)
                            ])
                        )
                    # 即使没有变化也显示当前好感度
                    elif plugin.get_config().get("display_value_always", False):
                        await ctx.reply(
                            MessageChain([
                                Plain(text=f"心动值：{value_game.get_value()}")
                            ])
                        )

                # 阻止默认的流水线处理流程，避免重复回复
                ctx.prevent_default()

                logger.info(f"群聊 {group_id} 回复用户 {user_name}: {response}")

            except Exception as e:
                logger.error(f"处理群聊消息失败: {e}", exc_info=True)
                await ctx.reply(
                    MessageChain([
                        Plain(text="抱歉，我现在无法回复消息。")
                    ])
                )

    async def should_respond(self, group_id: str, text: str) -> bool:
        """判断是否应该在群聊中回复消息"""
        logger.info(f"should_respond 被调用，group_id: {group_id}, text: {text}")
        return True  # 总是回复群聊消息

    async def should_repeat(self, group_id: str, text: str) -> bool:
        """判断是否应该复读消息"""
        # 初始化群聊记录
        if group_id not in self.repeat_messages:
            self.repeat_messages[group_id] = {}

        # 更新消息计数
        if text not in self.repeat_messages[group_id]:
            self.repeat_messages[group_id][text] = 1
        else:
            self.repeat_messages[group_id][text] += 1

        # 获取插件实例
        plugin = self.plugin
        
        # 获取触发阈值
        threshold = plugin.get_config().get("repeat_trigger", 2)

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

import logging
from langbot_plugin.api import Command, ExecuteContext
from langbot_plugin.api.entities.builtin.platform.message import Plain, MessageChain

logger = logging.getLogger(__name__)

class MemoryCommand(Command):
    async def view_memory(self, ctx: ExecuteContext):
        """查看用户记忆"""
        try:
            logger.info("收到查看记忆命令")
            
            # 获取用户信息
            if hasattr(ctx.query.sender, 'user_id'):
                user_id = str(ctx.query.sender.user_id)
                user_name = ctx.query.sender.nickname or f"用户{user_id}"
            else:
                await ctx.reply(
                    MessageChain([Plain(text="无法获取用户信息")])
                )
                return
            
            # 初始化记忆系统
            if not hasattr(self.plugin.memories, 'user_name') or self.plugin.memories.user_name != user_name:
                await self.plugin.memories.initialize(user_name, "Waifu")
            
            # 获取短期记忆
            short_term_memory = self.plugin.memories.get_short_term_memory_text()
            
            # 构造回复
            response = "短期记忆：\n"
            if short_term_memory:
                # 只显示最近的5条消息
                recent_messages = short_term_memory.split("\n")[-10:]
                response += "\n".join(recent_messages)
            else:
                response += "暂无短期记忆"
            
            # 获取长期记忆数量
            long_term_count = len(self.plugin.memories.long_term_memories)
            response += f"\n\n长期记忆数量：{long_term_count}"
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text=response)
                ])
            )
            
            logger.info(f"用户 {user_name} 查看了记忆")
            
        except Exception as e:
            logger.error(f"查看记忆失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="查看记忆失败，请稍后重试")])
            )
    
    async def clear_memory(self, ctx: ExecuteContext):
        """清除用户记忆"""
        try:
            logger.info("收到清除记忆命令")
            
            # 获取用户信息
            if hasattr(ctx.query.sender, 'user_id'):
                user_id = str(ctx.query.sender.user_id)
                user_name = ctx.query.sender.nickname or f"用户{user_id}"
            else:
                await ctx.reply(
                    MessageChain([Plain(text="无法获取用户信息")])
                )
                return
            
            # 初始化记忆系统
            if not hasattr(self.plugin.memories, 'user_name') or self.plugin.memories.user_name != user_name:
                await self.plugin.memories.initialize(user_name, "Waifu")
            
            # 清除记忆
            await self.plugin.memories.clear_all_memories()
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text="你的所有记忆已清除")
                ])
            )
            
            logger.info(f"用户 {user_name} 清除了记忆")
            
        except Exception as e:
            logger.error(f"清除记忆失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="清除记忆失败，请稍后重试")])
            )
    
    async def edit_memory(self, ctx: ExecuteContext):
        """编辑记忆内容（管理员）"""
        try:
            logger.info("收到编辑记忆命令")
            
            # 检查是否为管理员
            config = self.plugin.get_config()
            admin_ids = config.get("admin_ids", [])
            user_id = str(ctx.query.sender.user_id)
            
            if user_id not in admin_ids:
                await ctx.reply(
                    MessageChain([Plain(text="权限不足，只有管理员可以使用此命令")])
                )
                return
            
            # 获取参数
            args = ctx.query.args
            if len(args) < 3:
                await ctx.reply(
                    MessageChain([Plain(text="使用方法：/memory edit <user_id> <memory_id> <content>")])
                )
                return
            
            target_user_id = args[0]
            memory_id = args[1]
            content = " ".join(args[2:])
            
            # 加载目标用户的记忆
            # 注意：这里需要实现加载指定用户记忆的功能
            await ctx.reply(
                MessageChain([Plain(text="当前版本暂不支持编辑记忆功能")])
            )
            
        except Exception as e:
            logger.error(f"编辑记忆失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="编辑记忆失败，请稍后重试")])
            )

# 创建命令实例
command = MemoryCommand()

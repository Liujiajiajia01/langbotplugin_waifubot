import logging
from langbot_plugin.api import Command, ExecuteContext
from langbot_plugin.api.entities.builtin.platform.message import Plain, MessageChain

logger = logging.getLogger(__name__)

class AffectionCommand(Command):
    async def check_affection(self, ctx: ExecuteContext):
        """查看当前用户好感度"""
        try:
            logger.info("收到好感度查询命令")
            
            # 获取用户ID
            if hasattr(ctx.query.sender, 'user_id'):
                user_id = str(ctx.query.sender.user_id)
                user_name = ctx.query.sender.nickname or f"用户{user_id}"
            else:
                await ctx.reply(
                    MessageChain([Plain(text="无法获取用户信息")])
                )
                return
            
            # 判断是群聊还是私聊
            is_group = hasattr(ctx.query, 'group')
            if is_group:
                group_id = str(ctx.query.group.id)
                launcher_id = f"group_{group_id}_{user_id}"
            else:
                launcher_id = user_id
            
            # 加载好感度系统
            await self.plugin.value_game.load_config(
                character=self.plugin.get_config().get("character", "default"),
                launcher_id=launcher_id,
                launcher_type="group" if is_group else "person"
            )
            
            # 获取好感度
            affection = self.plugin.value_game.get_value()
            description = self.plugin.value_game.get_manner_description()
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text=f"{user_name}，你的当前好感度是：{affection}/100\n{description}")
                ])
            )
            
            logger.info(f"用户 {user_name} 查看了好感度: {affection}")
            
        except Exception as e:
            logger.error(f"查看好感度失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="查看好感度失败，请稍后重试")])
            )
    
    async def set_affection(self, ctx: ExecuteContext):
        """设置用户好感度（管理员）"""
        try:
            logger.info("收到设置好感度命令")
            
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
            if len(args) < 2:
                await ctx.reply(
                    MessageChain([Plain(text="使用方法：/affection set <user_id> <value>")])
                )
                return
            
            target_user_id = args[0]
            try:
                value = int(args[1])
            except ValueError:
                await ctx.reply(
                    MessageChain([Plain(text="好感度必须是整数")])
                )
                return
            
            # 判断是群聊还是私聊
            is_group = hasattr(ctx.query, 'group')
            if is_group:
                group_id = str(ctx.query.group.id)
                launcher_id = f"group_{group_id}_{target_user_id}"
            else:
                launcher_id = target_user_id
            
            # 加载好感度系统
            await self.plugin.value_game.load_config(
                character=self.plugin.get_config().get("character", "default"),
                launcher_id=launcher_id,
                launcher_type="group" if is_group else "person"
            )
            
            # 设置好感度
            self.plugin.value_game.change_manner_value(value - self.plugin.value_game.get_value())
            new_affection = self.plugin.value_game.get_value()
            
            # 发送回复
            await ctx.reply(
                MessageChain([
                    Plain(text=f"已将用户 {target_user_id} 的好感度设置为：{new_affection}/100")
                ])
            )
            
            logger.info(f"管理员 {user_id} 将用户 {target_user_id} 的好感度设置为: {new_affection}")
            
        except Exception as e:
            logger.error(f"设置好感度失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="设置好感度失败，请稍后重试")])
            )
    
    async def list_affection(self, ctx: ExecuteContext):
        """列出所有用户好感度（管理员）"""
        try:
            logger.info("收到列出好感度命令")
            
            # 检查是否为管理员
            config = self.plugin.get_config()
            admin_ids = config.get("admin_ids", [])
            user_id = str(ctx.query.sender.user_id)
            
            if user_id not in admin_ids:
                await ctx.reply(
                    MessageChain([Plain(text="权限不足，只有管理员可以使用此命令")])
                )
                return
            
            # 由于我们的好感度是按用户ID和场景存储的，这里简化处理
            # 实际实现中，应该从存储中获取所有好感度数据
            await ctx.reply(
                MessageChain([Plain(text="当前版本暂不支持列出所有用户好感度")])
            )
            
        except Exception as e:
            logger.error(f"列出好感度失败: {e}", exc_info=True)
            await ctx.reply(
                MessageChain([Plain(text="列出好感度失败，请稍后重试")])
            )

# 创建命令实例
command = AffectionCommand()

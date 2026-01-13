import json
import logging
import time
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class Memory:
    def __init__(self, plugin):
        self.plugin = plugin
        self.user_id = ""
        self.user_name = ""
        self.bot_name = ""
        self.short_term_memory = []
        self.long_term_memories = []
        self.session_memories = []
        
        # 配置参数
        self.short_term_memory_size = 2000
        self.retrieve_top_n = 3
        self.recall_once = 3
        self.session_memories_size = 6
        self.summary_max_tags = 30
    
    async def initialize(self, user_name: str, bot_name: str, user_id: str = None):
        """
        初始化记忆系统
        :param user_name: 用户名称
        :param bot_name: 机器人名称
        :param user_id: 用户ID（唯一标识）
        """
        self.user_name = user_name
        self.bot_name = bot_name
        self.user_id = user_id if user_id else user_name  # 如果没有提供ID，使用用户名作为备选
        
        # 加载配置
        config = self.plugin.get_config()
        self.short_term_memory_size = config.get("short_term_memory_size", 2000)
        self.retrieve_top_n = config.get("retrieve_top_n", 3)
        self.recall_once = config.get("recall_once", 3)
        self.session_memories_size = config.get("session_memories_size", 6)
        self.summary_max_tags = config.get("summary_max_tags", 30)
        
        # 加载长期记忆
        await self.load_long_term_memories()
        logger.info("记忆系统初始化完成")
    
    async def load_long_term_memories(self):
        """
        加载长期记忆
        """
        try:
            memory_key = f"long_term_memories_{self.user_id}"
            memory_data = await self.plugin.get_plugin_storage(memory_key)
            if memory_data:
                self.long_term_memories = json.loads(memory_data.decode("utf-8"))
                logger.info(f"加载了 {len(self.long_term_memories)} 条长期记忆")
        except Exception as e:
            logger.error(f"加载长期记忆失败: {e}", exc_info=True)
            self.long_term_memories = []
    
    async def save_long_term_memories(self):
        """
        保存长期记忆
        """
        try:
            memory_key = f"long_term_memories_{self.user_id}"
            memory_data = json.dumps(self.long_term_memories).encode("utf-8")
            await self.plugin.set_plugin_storage(memory_key, memory_data)
            logger.info(f"保存了 {len(self.long_term_memories)} 条长期记忆")
        except Exception as e:
            logger.error(f"保存长期记忆失败: {e}", exc_info=True)
    
    async def add_short_term_memory(self, speaker: str, content: str):
        """
        添加短期记忆
        :param speaker: 发言者（user/bot）
        :param content: 发言内容
        """
        memory_item = {
            "speaker": speaker,
            "content": content,
            "timestamp": time.time()
        }
        
        self.short_term_memory.append(memory_item)
        
        # 检查短期记忆大小，如果超过限制则清理
        total_length = sum(len(item["content"]) for item in self.short_term_memory)
        while total_length > self.short_term_memory_size and len(self.short_term_memory) > 1:
            removed_item = self.short_term_memory.pop(0)
            total_length -= len(removed_item["content"])
        
        logger.debug(f"添加短期记忆: {speaker} - {content}")
    
    async def summarize_long_term_memory(self):
        """
        总结长期记忆
        """
        if not self.short_term_memory:
            return
        
        # 构建总结提示
        memory_text = "\n".join([f"{item['speaker']}: {item['content']}" for item in self.short_term_memory])
        prompt = f"请总结以下对话的重要信息，提取关键词和关键事件，最多使用{self.summary_max_tags}个关键词：\n\n{memory_text}"
        
        # 调用LLM生成总结
        from langbot_plugin.api.entities.builtin.provider.message import Message
        
        try:
            llm_models = await self.plugin.get_llm_models()
            if not llm_models:
                logger.error("没有可用的LLM模型用于总结记忆")
                return
            
            messages = [
                Message(role="system", content="你是一个记忆总结助手，需要提取对话中的重要信息和关键词。"),
                Message(role="user", content=prompt)
            ]
            
            response = await self.plugin.invoke_llm(
                llm_model_uuid=llm_models[0],
                messages=messages,
                funcs=[],
                extra_args={}
            )
            
            summary = response.content
            logger.info(f"生成长期记忆总结: {summary}")
            
            # 保存长期记忆
            long_term_memory = {
                "id": str(time.time()),
                "content": summary,
                "timestamp": time.time(),
                "tags": await self._extract_tags(summary),
                "importance": 0.5
            }
            
            self.long_term_memories.append(long_term_memory)
            await self.save_long_term_memories()
            
        except Exception as e:
            logger.error(f"总结长期记忆失败: {e}", exc_info=True)
    
    async def _extract_tags(self, text: str) -> List[str]:
        """
        从文本中提取关键词标签
        :param text: 文本内容
        :return: 关键词标签列表
        """
        try:
            # 使用text_analyzer提取关键词
            counter, i18n_list, related_list = await self.plugin.text_analyzer.term_freq(text)
            
            # 合并所有可能的标签
            tags = list(counter.keys()) + i18n_list + related_list
            
            # 按词频排序并限制数量
            sorted_tags = sorted(tags, key=lambda x: counter.get(x, 0), reverse=True)
            return sorted_tags[:self.summary_max_tags]
            
        except Exception as e:
            logger.error(f"提取标签失败: {e}", exc_info=True)
            return []
    
    async def retrieve_related_memories(self, query: str) -> List[Dict[str, Any]]:
        """
        检索相关的长期记忆
        :param query: 查询内容
        :return: 相关记忆列表
        """
        if not self.long_term_memories:
            return []
        
        try:
            # 简单的关键词匹配
            query_words = set(query.split())
            related_memories = []
            
            for memory in self.long_term_memories:
                memory_content = memory["content"].lower()
                # 计算关键词匹配度
                match_count = sum(1 for word in query_words if word.lower() in memory_content)
                if match_count > 0:
                    # 添加匹配度分数
                    memory_with_score = memory.copy()
                    memory_with_score["match_score"] = match_count / len(query_words)
                    related_memories.append(memory_with_score)
            
            # 按匹配度排序并返回前N条
            related_memories.sort(key=lambda x: x["match_score"], reverse=True)
            return related_memories[:self.retrieve_top_n]
            
        except Exception as e:
            logger.error(f"检索相关记忆失败: {e}", exc_info=True)
            return []
    
    async def update_session_memories(self, query: str):
        """
        更新会话记忆池
        :param query: 当前查询内容
        """
        # 检索相关记忆
        related_memories = await self.retrieve_related_memories(query)
        
        # 将相关记忆添加到会话记忆池
        for memory in related_memories:
            if memory not in self.session_memories:
                self.session_memories.append(memory)
                # 如果会话记忆池超过限制，移除最旧的记忆
                if len(self.session_memories) > self.session_memories_size:
                    self.session_memories.pop(0)
    
    def get_short_term_memory_text(self) -> str:
        """
        获取短期记忆文本
        :return: 短期记忆文本
        """
        return "\n".join([f"{item['speaker']}: {item['content']}" for item in self.short_term_memory])
    
    def get_session_memories_text(self) -> str:
        """
        获取会话记忆池文本
        :return: 会话记忆池文本
        """
        if not self.session_memories:
            return ""
        
        memory_text = "长期记忆：\n"
        for memory in self.session_memories[:self.recall_once]:
            memory_text += f"- {memory['content']}\n"
        
        return memory_text
    
    def get_last_speaker(self, memories: List[Dict[str, Any]]) -> str:
        """
        获取最后发言者
        :param memories: 记忆列表
        :return: 最后发言者
        """
        if not memories:
            return ""
        return memories[-1]["speaker"]
    
    def get_last_content(self, memories: List[Dict[str, Any]]) -> str:
        """
        获取最后一条消息内容
        :param memories: 记忆列表
        :return: 最后一条消息内容
        """
        if not memories:
            return ""
        return memories[-1]["content"]
    
    async def clear_all_memories(self):
        """
        清除所有记忆
        """
        self.short_term_memory = []
        self.long_term_memories = []
        self.session_memories = []
        
        # 清除存储的长期记忆
        try:
            memory_key = f"long_term_memories_{self.user_name}"
            await self.plugin.delete_plugin_storage(memory_key)
            logger.info("所有记忆已清除")
        except Exception as e:
            logger.error(f"清除记忆失败: {e}", exc_info=True)

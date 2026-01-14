import json
import logging
import time
import re
from typing import List, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict

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
        
        # 最新情感状态（供其他模块使用）
        self.current_emotion_score = 0.0
        self.current_emotion_type = "neutral"
        
        # 配置参数
        self.short_term_memory_size = 2000
        self.retrieve_top_n = 3
        self.recall_once = 3
        self.session_memories_size = 6
        self.summary_max_tags = 30
        
        # 增强的记忆参数
        self.memory_decay_rate = 0.95  # 记忆衰减率
        self.memory_weight_max = 1.0  # 最大记忆权重
        self.memory_boost_rate = 0.15  # 记忆激活时的权重提升率
        self.emotion_weight_factor = 1.5  # 情感内容的权重因子
        
        # 记忆分层参数
        self.memory_levels = {
            "core": 0.8,  # 核心记忆阈值
            "important": 0.6,  # 重要记忆阈值
            "normal": 0.4,  # 普通记忆阈值
            "trivial": 0.2   # 琐碎记忆阈值
        }
        
        # 情感关键词库
        self.emotion_keywords = {
            "positive": ["喜欢", "爱", "开心", "高兴", "快乐", "幸福", "满足", "兴奋", "感激"],
            "negative": ["不喜欢", "讨厌", "难过", "伤心", "生气", "愤怒", "失望", "焦虑", "害怕"],
            "neutral": ["知道", "了解", "明白", "收到", "好的", "是的", "可以", "谢谢"]
        }
        
        # 记忆关联网络
        self.memory_graph = defaultdict(list)  # {memory_id: [related_memory_id1, related_memory_id2, ...]}
    
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
        
        # 加载配置，大幅增加短期记忆大小以保留更多用户信息
        config = self.plugin.get_config()
        self.short_term_memory_size = config.get("short_term_memory_size", 10000)  # 短期记忆的最大长度
        self.retrieve_top_n = config.get("retrieve_top_n", 8)  # 每次提取的相关长期记忆数量
        self.recall_once = config.get("recall_once", 8)  # 每次召回到记忆池中的长期记忆数量
        self.session_memories_size = config.get("session_memories_size", 15)  # 记忆池容量
        self.summary_max_tags = config.get("summary_max_tags", 50)  # 每段长期记忆的最大标签数量
        self.analyze_max_conversations = config.get("analyze_max_conversations", 9)  # 用于生成分析的最大对话数量
        
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
            else:
                logger.info("没有找到长期记忆，将使用空记忆列表")
                self.long_term_memories = []
        except Exception as e:
            # 如果是存储键未找到的错误，优雅处理
            if "Storage with key" in str(e) and "not found" in str(e):
                logger.info("首次使用，尚未创建长期记忆存储")
                self.long_term_memories = []
            else:
                logger.error(f"加载长期记忆失败: {e}", exc_info=True)
                self.long_term_memories = []
    
    async def save_long_term_memories(self):
        """
        保存长期记忆到文件
        """
        try:
            # 创建用户ID对应的文件夹
            import os
            user_id = self.user_id.replace("group_", "")  # 移除group_前缀，统一用户ID
            memory_dir = f"data/memories/{user_id}"
            os.makedirs(memory_dir, exist_ok=True)
            
            # 保存长期记忆到JSON文件
            memory_file = os.path.join(memory_dir, "long_term_memories.json")
            with open(memory_file, "w", encoding="utf-8") as f:
                json.dump(self.long_term_memories, f, ensure_ascii=False, indent=4)
            
            logger.info(f"保存了 {len(self.long_term_memories)} 条长期记忆到 {memory_file}")
        except Exception as e:
            logger.error(f"保存长期记忆失败: {e}", exc_info=True)
            # 回退到使用插件存储
            try:
                memory_key = f"long_term_memories_{self.user_id}"
                memory_data = json.dumps(self.long_term_memories).encode("utf-8")
                await self.plugin.set_plugin_storage(memory_key, memory_data)
                logger.info(f"回退到插件存储，保存了 {len(self.long_term_memories)} 条长期记忆")
            except Exception as backup_e:
                logger.error(f"回退到插件存储也失败了: {backup_e}", exc_info=True)
    
    async def load_long_term_memories(self):
        """
        从文件加载长期记忆
        """
        try:
            # 尝试从文件加载
            import os
            user_id = self.user_id.replace("group_", "")  # 移除group_前缀，统一用户ID
            memory_file = f"data/memories/{user_id}/long_term_memories.json"
            
            if os.path.exists(memory_file):
                with open(memory_file, "r", encoding="utf-8") as f:
                    self.long_term_memories = json.load(f)
                logger.info(f"从 {memory_file} 加载了 {len(self.long_term_memories)} 条长期记忆")
            else:
                self.long_term_memories = []
                logger.info("没有找到长期记忆文件，开始新的记忆")
        except Exception as e:
            logger.error(f"从文件加载长期记忆失败: {e}", exc_info=True)
            # 回退到使用插件存储
            try:
                memory_key = f"long_term_memories_{self.user_id}"
                memory_data = await self.plugin.get_plugin_storage(memory_key)
                if memory_data:
                    self.long_term_memories = json.loads(memory_data.decode("utf-8"))
                    logger.info(f"回退到插件存储，加载了 {len(self.long_term_memories)} 条长期记忆")
                else:
                    self.long_term_memories = []
            except Exception as backup_e:
                logger.error(f"回退到插件存储也失败了: {backup_e}", exc_info=True)
                self.long_term_memories = []
    
    async def add_short_term_memory(self, speaker: str, content: str):
        """
        添加短期记忆
        :param speaker: 发言者（user/bot）
        :param content: 发言内容
        """
        # 分析情感倾向
        emotion_score, emotion_type = self._analyze_emotion(content)
        
        # 创建记忆项，包含情感信息
        memory_item = {
            "speaker": speaker,
            "content": content,
            "timestamp": time.time(),
            "emotion_score": emotion_score,
            "emotion_type": emotion_type
        }
        
        self.short_term_memory.append(memory_item)
        
        # 存储最新的情感分析结果，供其他模块使用
        self.current_emotion_score = emotion_score
        self.current_emotion_type = emotion_type
        
        # 检查短期记忆大小，如果超过限制则总结为长期记忆
        total_length = self._calc_short_term_memory_size()
        logger.info(f"当前短期记忆大小: {total_length} 字符, 允许最大值: {self.short_term_memory_size} 字符")
        
        # 确保重要信息（如用户的穿着、喜好等）能够被及时总结
        # 检查最新的用户消息是否包含重要信息关键词
        if speaker == "user" and any(keyword in content for keyword in ["穿", "衣服", "颜色", "喜欢", "爱好", "生日", "年龄"]):
            logger.info(f"检测到重要信息，提前总结长期记忆: {content}")
            await self.summarize_long_term_memory()
        elif total_length > self.short_term_memory_size:
            logger.info("短期记忆超过限制，总结长期记忆")
            await self.summarize_long_term_memory()
        
        # 只在短期记忆达到阈值时才进行总结，避免每次消息都调用LLM
        if total_length >= self.short_term_memory_size:
            logger.info("短期记忆达到阈值，开始总结为长期记忆")
            await self.summarize_long_term_memory()  # 同步执行总结
        
        logger.debug(f"添加短期记忆: {speaker} - {content} [情感: {emotion_type}, 分数: {emotion_score:.2f}]")
    
    def _analyze_emotion(self, text: str) -> Tuple[float, str]:
        """
        分析文本的情感倾向
        :param text: 要分析的文本
        :return: (情感分数, 情感类型)
        """
        text_lower = text.lower()
        emotion_counts = {
            "positive": 0,
            "negative": 0,
            "neutral": 0
        }
        
        # 统计各类情感关键词的出现次数
        for emotion, keywords in self.emotion_keywords.items():
            for keyword in keywords:
                emotion_counts[emotion] += len(re.findall(r'\b' + re.escape(keyword) + r'\b', text_lower))
        
        # 计算情感分数
        total = sum(emotion_counts.values())
        if total == 0:
            return 0.0, "neutral"
        
        # 正面情感加1分，负面情感减1分
        score = (emotion_counts["positive"] - emotion_counts["negative"]) / total
        
        # 确定情感类型
        if score > 0.3:
            return score, "positive"
        elif score < -0.3:
            return score, "negative"
        else:
            return score, "neutral"
        
    def _calc_short_term_memory_size(self) -> int:
        """
        计算短期记忆的总长度
        :return: 总长度（字符数）
        """
        return sum(len(item["content"]) for item in self.short_term_memory)
    
    async def summarize_long_term_memory(self):
        """
        总结长期记忆
        """
        if not self.short_term_memory:
            return
            
        try:
            # 分析短期记忆的整体情感趋势
            overall_emotion = self._analyze_overall_emotion()
            
            # 使用所有短期记忆进行总结，保留完整上下文
            memory_lines = []
            for item in self.short_term_memory:
                emotion_mark = f" [{item['emotion_type']}]" if item['emotion_type'] != "neutral" else ""
                memory_lines.append(f"{item['speaker']}: {item['content']}{emotion_mark}")
            
            memory_text = "\n".join(memory_lines)
            
            # 使用简单的方式总结长期记忆，避免LLM超时
            # 提取关键词标签
            tags = await self._extract_tags(memory_text)
            
            # 生成简洁的总结
            user_messages = [item['content'] for item in self.short_term_memory if item['speaker'] == 'user']
            if not user_messages:
                return
                
            # 简单总结：用户提到的主要内容
            summary = f"用户与机器人进行了对话，主要提到了：{', '.join(user_messages[-3:])}"
            
            # 如果有情感信息，添加到总结中
            if overall_emotion['score'] != 0:
                summary += f" 对话情感主要是{overall_emotion['type']}。"
            
            # 创建记忆项
            memory_item = {
                "id": str(time.time()),
                "content": summary,
                "tags": tags[:self.summary_max_tags],  # 限制标签数量
                "timestamp": time.time(),
                "emotion_type": overall_emotion['type'],
                "emotion_score": overall_emotion['score'],
                "weight": 0.5
            }
            
            # 添加到长期记忆
            self.long_term_memories.append(memory_item)
            
            # 保存长期记忆
            await self.save_long_term_memories()
            
            # 清空短期记忆，只保留最新的几条
            self.short_term_memory = self.short_term_memory[-5:]
            
            logger.info(f"长期记忆总结完成，添加了新的记忆项")
            return
            
            # 以下是原来的LLM总结方式，暂时注释掉以避免超时
            # 构建增强的总结提示，包含情感分析信息，特别强调保存用户所有对话内容
            # prompt = f"基于以下对话内容，生成独立的新总结：\n\n当前对话:\"{memory_text}\"\n\n对话整体情感趋势: {overall_emotion['type']} (分数: {overall_emotion['score']:.2f})\n\n总结要求：\n1. 限制在200字以内\n2. 使用中文，以过去式书写\n3. 突出情感重点和关键事件\n4. 保持客观中立\n5. 必须包含用户所有提到的关键词和关键信息，如穿着、喜好、计划等\n\n你需要在总结的末尾包含：\n1. 情感标签：反映对话的主要情感色彩\n2. 关键概念：按重要性排序的核心词汇，必须包含用户提到的所有关键词\n\n格式要求：\n总结内容\n\n情感标签：[标签1, 标签2, ...]\n关键概念：[概念1, 概念2, ...]\n"
            
            logger.debug(f"总结长期记忆提示词长度: {len(prompt)} 字符")
            
            # 调用LLM生成总结
            from langbot_plugin.api.entities.builtin.provider.message import Message
            
            llm_models = await self.plugin.get_llm_models()
            logger.debug(f"获取到的LLM模型列表: {llm_models}")
            if not llm_models:
                logger.error("没有可用的LLM模型用于总结记忆")
                return
            
            # 正确处理模型列表，根据返回类型选择模型
            if isinstance(llm_models, list):
                if llm_models and isinstance(llm_models[0], dict):
                    # 模型列表是字典列表，包含模型详细信息
                    # 选择距离当前时间最近的模型（created_at最大的模型）
                    latest_model = None
                    latest_time = None
                    
                    for model in llm_models:
                        created_at = model.get('created_at', '')
                        if created_at:
                            if not latest_time or created_at > latest_time:
                                latest_time = created_at
                                latest_model = model
                    
                    if latest_model:
                        llm_model_uuid = latest_model.get('uuid') or latest_model.get('id')
                        logger.debug(f"使用最新模型: {latest_model.get('name')} (UUID: {llm_model_uuid}, 创建时间: {latest_model.get('created_at')})")
                    else:
                        # 如果没有找到带created_at的模型，退而求其次使用第一个模型
                        model_info = llm_models[0]
                        llm_model_uuid = model_info.get('uuid') or model_info.get('id')
                        logger.debug(f"没有找到带created_at的模型，使用第一个模型: {model_info.get('name')} (UUID: {llm_model_uuid})")
                else:
                    # 模型列表是UUID字符串列表，无法根据时间选择，使用第一个模型
                    llm_model_uuid = str(llm_models[0])
                    logger.debug(f"模型列表是UUID字符串列表，使用第一个模型UUID: {llm_model_uuid}")
            else:
                logger.error("获取到的LLM模型列表格式错误")
                return
            
            messages = [
                Message(role="system", content="你是一个专业的对话总结助手，能够提取对话的核心内容、情感色彩和关键信息。"),
                Message(role="user", content=prompt)
            ]
            
            # 设置合理的超时时间
            extra_args = {
                "timeout": 30  # 设置30秒超时
            }
            
            # 获取API密钥
            api_key = self.plugin.get_config().get("api_key", "")
            
            # 在extra_args中传递API密钥
            if api_key:
                extra_args["api_key"] = api_key
                logger.debug(f"在extra_args中使用API密钥: {api_key[:10]}...{api_key[-10:]}")
            
            # 单次调用，不重试，避免超时累积
            response = await self.plugin.invoke_llm(
                llm_model_uuid=llm_model_uuid,
                messages=messages,
                extra_args=extra_args
            )
            
            summary = response.content
            logger.info(f"生成长期记忆总结: {summary}")
            
            # 提取总结中的情感标签和关键概念
            emotion_tags = []
            key_concepts = []
            
            # 解析情感标签
            emotion_match = re.search(r'情感标签：\[(.*?)\]', summary)
            if emotion_match:
                emotion_tags = [tag.strip() for tag in emotion_match.group(1).split(',')]
            
            # 解析关键概念
            concept_match = re.search(r'关键概念：\[(.*?)\]', summary)
            if concept_match:
                key_concepts = [concept.strip() for concept in concept_match.group(1).split(',')]
            
            # 如果解析失败，使用默认提取方法
            if not key_concepts:
                key_concepts = await self._extract_tags(summary)
            
            # 计算记忆重要性，基于情感分数和内容长度
            importance = self._calculate_memory_importance(overall_emotion['score'], summary)
            
            # 保存长期记忆
            long_term_memory = {
                "id": str(time.time()),
                "content": summary,
                "timestamp": time.time(),
                "tags": key_concepts,
                "emotion_tags": emotion_tags,
                "importance": importance,
                "emotion_score": overall_emotion['score'],
                "emotion_type": overall_emotion['type'],
                "weight": importance  # 初始权重等于重要性
            }
            
            self.long_term_memories.append(long_term_memory)
            
            # 更新记忆关联网络
            self._update_memory_graph(long_term_memory)
            
            # 保存长期记忆
            await self.save_long_term_memories()
            
            # 总结完成后，只保留短期记忆的最后一部分（1/3）
            max_remain = self.short_term_memory_size // 3
            if max_remain > 0:
                self._drop_short_term_memory(max_remain)
            
        except Exception as e:
            logger.error(f"总结长期记忆失败: {e}", exc_info=True)
    
    def _analyze_overall_emotion(self) -> Dict[str, Any]:
        """
        分析短期记忆的整体情感趋势
        :return: {"type": 情感类型, "score": 情感分数}
        """
        if not self.short_term_memory:
            return {"type": "neutral", "score": 0.0}
        
        total_score = sum(item.get("emotion_score", 0.0) for item in self.short_term_memory)
        avg_score = total_score / len(self.short_term_memory)
        
        if avg_score > 0.3:
            return {"type": "positive", "score": avg_score}
        elif avg_score < -0.3:
            return {"type": "negative", "score": avg_score}
        else:
            return {"type": "neutral", "score": avg_score}
    
    def _calculate_memory_importance(self, emotion_score: float, content: str) -> float:
        """
        计算记忆的重要性
        :param emotion_score: 情感分数
        :param content: 记忆内容
        :return: 重要性分数（0-1）
        """
        # 基础重要性基于内容长度
        base_importance = min(len(content) / 200, 1.0)
        
        # 情感因素调整
        emotion_factor = 1.0 + abs(emotion_score) * self.emotion_weight_factor
        
        # 最终重要性
        importance = base_importance * emotion_factor
        
        # 限制在0-1之间
        return min(max(importance, 0.1), 1.0)
    
    def _update_memory_graph(self, new_memory: Dict[str, Any]):
        """
        更新记忆关联网络
        :param new_memory: 新的长期记忆
        """
        new_memory_id = new_memory["id"]
        new_tags = new_memory.get("tags", [])
        
        # 寻找与新记忆相关的现有记忆
        for memory in self.long_term_memories[:-1]:  # 排除刚添加的记忆
            memory_tags = memory.get("tags", [])
            # 计算标签相似度
            common_tags = set(new_tags).intersection(set(memory_tags))
            if len(common_tags) >= 2:  # 如果有2个或更多共同标签，认为相关
                # 添加双向关联
                self.memory_graph[new_memory_id].append(memory["id"])
                self.memory_graph[memory["id"]].append(new_memory_id)
                
        logger.debug(f"更新记忆关联网络：新记忆 {new_memory_id} 与 {len(self.memory_graph[new_memory_id])} 条现有记忆相关联")
    
    def _drop_short_term_memory(self, max_remain: int):
        """
        清理短期记忆，保留指定数量的最新记忆
        :param max_remain: 最多保留的记忆数量
        """
        if len(self.short_term_memory) > max_remain:
            removed_count = len(self.short_term_memory) - max_remain
            removed_items = self.short_term_memory[:removed_count]
            self.short_term_memory = self.short_term_memory[removed_count:]
            logger.info(f"清理了 {removed_count} 条短期记忆，保留了 {len(self.short_term_memory)} 条")
            for item in removed_items:
                logger.debug(f"移除的短期记忆: {item['speaker']} - {item['content'][:50]}...")
    
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
        检索相关的长期记忆（增强版）
        :param query: 查询内容
        :return: 相关记忆列表
        """
        if not self.long_term_memories:
            return []
        
        try:
            # 分析查询的情感倾向
            query_emotion_score, query_emotion_type = self._analyze_emotion(query)
            query_words = set(word.lower() for word in query.split())
            
            # 扩展查询关键词（如果有相关记忆网络）
            expanded_query = set(query_words)
            
            related_memories = []
            
            for memory in self.long_term_memories:
                memory_content = memory["content"].lower()
                memory_tags = set(tag.lower() for tag in memory.get("tags", []))
                memory_emotion_type = memory.get("emotion_type", "neutral")
                memory_emotion_score = memory.get("emotion_score", 0.0)
                memory_weight = memory.get("weight", 0.5)
                
                # 计算内容匹配度
                content_match_count = sum(1 for word in query_words if word in memory_content)
                # 计算标签匹配度
                tag_match_count = sum(1 for word in query_words if word in memory_tags)
                # 情感匹配度（相同情感类型加分）
                emotion_match = 1.0 if memory_emotion_type == query_emotion_type else 0.5
                # 情感强度匹配
                emotion_score_match = 1.0 - abs(memory_emotion_score - query_emotion_score)
                
                # 综合匹配度计算
                content_weight = 0.3
                tag_weight = 0.5
                emotion_weight = 0.2
                
                base_match = (content_match_count / max(len(query_words), 1)) * content_weight + \
                           (tag_match_count / max(len(memory_tags), 1)) * tag_weight + \
                           emotion_match * emotion_score_match * emotion_weight
                
                # 计算时间衰减因子
                time_delta = time.time() - memory["timestamp"]
                # 动态衰减：近期记忆衰减慢，远期记忆衰减快
                time_decay = max(0.1, 1 / (1 + (time_delta / (24 * 3600)) * 0.1))
                
                # 记忆权重调整（重要记忆权重更高）
                weight_factor = memory_weight
                
                # 最终匹配分数
                match_score = base_match * time_decay * weight_factor
                
                # 降低匹配阈值，确保更多相关记忆能够被检索到
                if match_score > 0.05:  # 设置更低的匹配阈值
                    memory_with_score = memory.copy()
                    memory_with_score["match_score"] = match_score
                    related_memories.append(memory_with_score)
                    
                # 对于包含用户穿着信息的记忆，给予额外分数
                if any(keyword in memory_content for keyword in ["穿", "衣服", "颜色"]):
                    match_score += 0.2
                    memory_with_score = memory.copy()
                    memory_with_score["match_score"] = match_score
                    related_memories.append(memory_with_score)
            
            # 按匹配度排序并返回前N条，增加返回数量
            related_memories.sort(key=lambda x: x["match_score"], reverse=True)
            
            # 更新被检索到的记忆的权重
            for memory in related_memories[:self.retrieve_top_n * 2]:  # 返回更多记忆
                memory_id = memory["id"]
                # 找到原始记忆并更新权重
                for original_memory in self.long_term_memories:
                    if original_memory["id"] == memory_id:
                        original_memory["weight"] = min(original_memory["weight"] + self.memory_boost_rate, self.memory_weight_max)
                        break
            
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
        
        # 将相关记忆添加到会话记忆池，参考persona_demo的记忆池管理
        for memory in related_memories:
            # 检查记忆是否已存在于会话记忆池
            memory_exists = False
            for i, existing_memory in enumerate(self.session_memories):
                if existing_memory["id"] == memory["id"]:
                    # 如果已存在，更新分数并移到最前面
                    self.session_memories.pop(i)
                    self.session_memories.append(memory)
                    memory_exists = True
                    break
            
            if not memory_exists:
                # 如果不存在，添加到会话记忆池
                self.session_memories.append(memory)
                # 如果会话记忆池超过限制，移除最旧的记忆
                if len(self.session_memories) > self.session_memories_size:
                    self.session_memories.pop(0)
        
        logger.debug(f"会话记忆池更新完成，当前包含 {len(self.session_memories)} 条记忆")
    
    def get_short_term_memory_text(self) -> str:
        """
        获取短期记忆文本
        :return: 短期记忆文本
        """
        # 保留更多短期记忆，增加最大长度
        max_length = 3000  # 增加到3000字符以内
        memory_text = ""
        
        # 从最新的记忆开始添加
        for memory in reversed(self.short_term_memory):
            memory_line = f"{memory['speaker']}: {memory['content']}\n"
            if len(memory_text) + len(memory_line) > max_length:
                break
            memory_text = memory_line + memory_text
        
        return memory_text.strip()
    
    def get_session_memories_text(self) -> str:
        """
        获取会话记忆池文本
        :return: 会话记忆池文本
        """
        if not self.session_memories:
            return ""
        
        memory_text = "长期记忆：\n"
        # 按匹配度排序并取前N条，参考persona_demo的记忆召回
        sorted_memories = sorted(self.session_memories, key=lambda x: x.get("match_score", 0), reverse=True)
        for memory in sorted_memories[:self.recall_once]:
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
            memory_key = f"long_term_memories_{self.user_id}"
            await self.plugin.delete_plugin_storage(memory_key)
            logger.info("所有记忆已清除")
        except Exception as e:
            logger.error(f"清除记忆失败: {e}", exc_info=True)

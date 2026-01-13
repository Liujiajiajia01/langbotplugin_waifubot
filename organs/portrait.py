import logging
import json
import os
from typing import Dict, Any

logger = logging.getLogger(__name__)

class UserPortrait:
    """用户画像分析类"""
    def __init__(self, plugin):
        self.plugin = plugin
        self.user_data = {}
        self.portrait_dir = os.path.join(plugin.get_plugin_data_dir(), "portraits")
        os.makedirs(self.portrait_dir, exist_ok=True)
    
    async def load_user_portrait(self, user_id: str):
        """加载用户画像"""
        file_path = os.path.join(self.portrait_dir, f"{user_id}.json")
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.user_data[user_id] = json.load(f)
            except Exception as e:
                logger.error(f"加载用户画像失败 {user_id}: {e}")
                self.user_data[user_id] = self._get_default_portrait()
        else:
            self.user_data[user_id] = self._get_default_portrait()
        
        return self.user_data[user_id]
    
    async def save_user_portrait(self, user_id: str):
        """保存用户画像"""
        if user_id in self.user_data:
            file_path = os.path.join(self.portrait_dir, f"{user_id}.json")
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.user_data[user_id], f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存用户画像失败 {user_id}: {e}")
    
    def _get_default_portrait(self) -> Dict[str, Any]:
        """获取默认用户画像"""
        return {
            "gender": "unknown",
            "age": "unknown",
            "interests": [],
            "personality": {},
            "topic_preferences": {},
            "interaction_count": 0,
            "last_interaction": None
        }
    
    async def analyze_user_message(self, user_id: str, message: str):
        """分析用户消息，更新画像"""
        if user_id not in self.user_data:
            await self.load_user_portrait(user_id)
        
        # 更新交互次数
        self.user_data[user_id]["interaction_count"] += 1
        
        # 简单的兴趣关键词提取
        interest_keywords = {
            "游戏": ["游戏", "原神", "LOL", "王者荣耀", "吃鸡"],
            "动漫": ["动漫", "二次元", "番剧", "漫画"],
            "音乐": ["音乐", "歌曲", "唱歌", "听歌"],
            "电影": ["电影", "看电影", "观影"],
            "阅读": ["看书", "阅读", "小说", "读书"]
        }
        
        for category, keywords in interest_keywords.items():
            for keyword in keywords:
                if keyword in message:
                    if category not in self.user_data[user_id]["interests"]:
                        self.user_data[user_id]["interests"].append(category)
                    # 更新话题偏好计数
                    self.user_data[user_id]["topic_preferences"][category] = \
                        self.user_data[user_id]["topic_preferences"].get(category, 0) + 1
                    break
        
        # 更新最后交互时间
        from datetime import datetime
        self.user_data[user_id]["last_interaction"] = datetime.now().isoformat()
        
        # 保存更新后的画像
        await self.save_user_portrait(user_id)
        
        return self.user_data[user_id]
    
    async def get_user_portrait(self, user_id: str) -> Dict[str, Any]:
        """获取用户画像"""
        if user_id not in self.user_data:
            await self.load_user_portrait(user_id)
        
        return self.user_data[user_id]
    
    async def update_user_info(self, user_id: str, info: Dict[str, Any]):
        """手动更新用户信息"""
        if user_id not in self.user_data:
            await self.load_user_portrait(user_id)
        
        self.user_data[user_id].update(info)
        await self.save_user_portrait(user_id)
    
    async def reset_user_portrait(self, user_id: str):
        """重置用户画像"""
        self.user_data[user_id] = self._get_default_portrait()
        await self.save_user_portrait(user_id)
    
    async def get_user_interest_ranking(self, user_id: str) -> Dict[str, int]:
        """获取用户兴趣偏好排序"""
        if user_id not in self.user_data:
            await self.load_user_portrait(user_id)
        
        return dict(sorted(
            self.user_data[user_id]["topic_preferences"].items(),
            key=lambda x: x[1],
            reverse=True
        ))
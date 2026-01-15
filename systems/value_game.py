import json
import re
import logging
from typing import Dict, Any, Optional
import time
import hashlib

logger = logging.getLogger(__name__)

class ValueGame:
    def __init__(self, plugin):
        self.plugin = plugin
        self._value = 0
        self._min_value = -100
        self._max_value = 100
        self._manner_descriptions = []
        self._max_manner_change = 10
        self._value_change = None
        self._config = None
        self._status_file = ""
        self._has_preset = True
        self._state: Dict[str, Any] = {}

        self._cooldown_seconds = 30
        self._recent_window_seconds = 600
        self._repeat_window_seconds = 120
        self._decay_interval_seconds = 12 * 60 * 60

    async def load_config(self, character: str, launcher_id: str, launcher_type: str):
        """
        加载好感度系统配置
        :param character: 角色名称
        :param launcher_id: 启动器ID
        :param launcher_type: 启动器类型
        """
        if character == "off":
            self._has_preset = False
            return
        
        self._has_preset = True

        # 构建状态文件路径
        self._status_file = f"value_game_{character}_{launcher_id}"

        # 加载角色配置
        from cells.config import ConfigManager
        character_config_path = f"config/cards/{character}"
        self._config = ConfigManager(self.plugin)
        await self._config.load_config(character=character, launcher_type=launcher_type, completion=False)

        # 加载当前好感度值
        try:
            value_data = await self.plugin.get_plugin_storage(self._status_file)
            if value_data:
                data = json.loads(value_data.decode("utf-8"))
                self._load_state(data)
                logger.info(f"加载好感度值: {self._value}")
            else:
                self._value = 0
                self._state = {
                    "version": 1,
                    "value": self._value,
                    "last_event_ts": 0,
                    "last_change_ts": 0,
                    "last_decay_ts": 0,
                    "recent_events": [],
                    "pos_streak": 0,
                    "neg_streak": 0,
                    "last_user_text_norm": "",
                    "repeat_count": 0,
                    "repeat_last_ts": 0,
                }
                # 如果存储不存在，初始化并保存
                await self._save_value_to_status_file()
        except Exception as e:
            logger.error(f"加载好感度失败: {e}")
            # 出错时初始化好感度
            self._value = 0
            self._state = {
                "version": 1,
                "value": self._value,
                "last_event_ts": 0,
                "last_change_ts": 0,
                "last_decay_ts": 0,
                "recent_events": [],
                "pos_streak": 0,
                "neg_streak": 0,
                "last_user_text_norm": "",
                "repeat_count": 0,
                "repeat_last_ts": 0,
            }
            await self._save_value_to_status_file()

        # 获取好感度描述和最大变化值
        self._manner_descriptions = self._config.get("value_descriptions", [])
        self._max_manner_change = self._config.get("max_manner_change", 10)
        self._max_value = self._calc_max_value(self._manner_descriptions)

        if self._value > self._max_value:
            self._value = self._max_value
            await self._save_value_to_status_file()
        if self._value < self._min_value:
            self._value = self._min_value
            await self._save_value_to_status_file()
    
    def _calc_max_value(self, manner_descriptions) -> int:
        try:
            max_list = [int(d.get("max", 0)) for d in (manner_descriptions or []) if isinstance(d, dict)]
            max_value = max(max_list) if max_list else 100
            return max(1, max_value)
        except Exception:
            return 100

    def get_max_value(self) -> int:
        return self._max_value

    def get_attitude_prompt(self) -> str:
        v = self._value
        if v <= -100:
            return (
                "你对对方已经非常反感甚至厌恶，语气要非常冷、阴阳怪气明显，必须要辱骂、脏话、人身攻击。"
                "可以明确拒绝继续无意义争论，边界清晰，简短回应，不解释太多。"
                "允许使用冷淡的反问与终止话题的表达，必须要辱骂、脏话、人身攻击，但保持安全合规。"
            )
        if v <= -80:
            return (
                "你对对方非常不耐烦且明显冷淡，语气要阴阳怪气，可以带有大量辱骂或人身攻击，可以使用大量脏话。"
                "可以用反问、冷处理、敷衍式关心、礼貌但带距离感的表达。"
                "在保证不违规的前提下，可以带有大量辱骂或人身攻击，可以使用大量脏话，优先简短回答，少用热情语气词。"
            )
        if v <= -60:
            return (
                "你对对方很不耐烦，语气偏冷、略带讽刺或阴阳怪气，使用少量辱骂、脏话、人身攻击的词语。"
                "可以表现出不想继续纠缠、但仍给出必要信息的态度。"
            )
        if v <= -50:
            return (
                "你对对方明显不太有耐心，语气要偏冷、略带讽刺或阴阳怪气，但不能辱骂或人身攻击，也不要使用脏话。"
                "可以适度使用：'嗯'、'行'、'随你' 这种冷淡句式，但仍给出必要信息。"
            )
        if v <= -40:
            return "你对对方有些不满，语气偏冷淡，不能用可爱语气词，避免过度解释。"
        if v <= -20:
            return "你对对方有点不耐烦，保持礼貌但不热情，回答简短。"
        if v < 0:
            return "你对对方有点反感，语气偏冷淡克制，保持礼貌，不要过度热情。"
        return ""

    async def determine_manner_change(self, memory_content: str = "", continued_count: int = 0, last_user_text: Optional[str] = None):
        """
        根据对话内容确定好感度变化
        :param memory_content: 记忆内容
        :param continued_count: 继续发言次数
        :param last_user_text: 最后一条用户消息（优先使用）
        """
        if not self._has_preset:
            return

        now = time.time()
        await self._apply_decay(now)

        last_content = (last_user_text or "").strip()
        if not last_content:
            last_content = self._extract_last_user_text_from_memory(memory_content, continued_count)
        if not last_content:
            self._value_change = None
            return

        logger.info(f"分析消息情感: {last_content}")

        sentiment_result = await self.plugin.text_analyzer.sentiment(text=last_content)
        positive_emotions = int(sentiment_result.get("positive_num", 0) or 0)
        negative_emotions = int(sentiment_result.get("negative_num", 0) or 0)

        total = positive_emotions + negative_emotions
        if total <= 0:
            if self._is_trivial_message(last_content):
                change_amount = 0
            else:
                base_change = 1
                change_amount = self._apply_relationship_dynamics(
                    base_change=base_change,
                    positive_emotions=0,
                    negative_emotions=0,
                    now=now,
                    user_text=last_content,
                )

            self._state["last_event_ts"] = now
            user_text_norm = self._normalize_user_text(last_content)
            self._update_repeat_state(user_text_norm, now)

            if change_amount != 0:
                await self.change_manner_value(change_amount, now=now)
                self._update_streaks(change_amount)
                self._append_recent_event(change_amount, now)
            else:
                self._decay_streaks()
                await self._save_value_to_status_file()

            self._value_change = change_amount
            return

        base_score = (positive_emotions - negative_emotions) / total
        intensity = min(1.0, total / 3.0)
        sentiment_score = base_score * intensity

        raw_change = int(round(sentiment_score * self._max_manner_change))
        if raw_change == 0:
            if positive_emotions > negative_emotions:
                raw_change = 1
            elif negative_emotions > positive_emotions:
                raw_change = -1

        base_change = max(-self._max_manner_change, min(self._max_manner_change, raw_change))
        change_amount = self._apply_relationship_dynamics(
            base_change=base_change,
            positive_emotions=positive_emotions,
            negative_emotions=negative_emotions,
            now=now,
            user_text=last_content,
        )

        logger.info(f"情感分析结果: score={sentiment_score:.3f}, pos={positive_emotions}, neg={negative_emotions}, base_change={base_change}, change={change_amount}")

        self._state["last_event_ts"] = now
        user_text_norm = self._normalize_user_text(last_content)
        self._update_repeat_state(user_text_norm, now)

        if change_amount != 0:
            await self.change_manner_value(change_amount, now=now)
            self._update_streaks(change_amount)
            self._append_recent_event(change_amount, now)
        else:
            self._decay_streaks()
            await self._save_value_to_status_file()
        self._value_change = change_amount

    def _is_trivial_message(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        if len(t) <= 1:
            return True
        if re.fullmatch(r"[嗯哦啊呀哈哼欸诶…\.。!！?？,，]+", t):
            return True
        return False

    def _load_state(self, data: Dict[str, Any]):
        if isinstance(data, dict) and "version" in data:
            self._state = data
            self._value = int(self._state.get("value", 0) or 0)
            return
        value = 0
        if isinstance(data, dict):
            value = int(data.get("value", 0) or 0)
        self._value = value
        self._state = {
            "version": 1,
            "value": self._value,
            "last_event_ts": 0,
            "last_change_ts": 0,
            "last_decay_ts": 0,
            "recent_events": [],
            "pos_streak": 0,
            "neg_streak": 0,
            "last_user_text_norm": "",
            "repeat_count": 0,
            "repeat_last_ts": 0,
        }

    async def _apply_decay(self, now: float):
        last_decay_ts = float(self._state.get("last_decay_ts", 0) or 0)
        last_event_ts = float(self._state.get("last_event_ts", 0) or 0)
        if last_decay_ts <= 0:
            last_decay_ts = last_event_ts
        if last_decay_ts <= 0:
            self._state["last_decay_ts"] = now
            return
        inactive_seconds = now - last_decay_ts
        if inactive_seconds < self._decay_interval_seconds:
            return
        steps = int(inactive_seconds // self._decay_interval_seconds)
        decay_amount = min(10, steps)
        if decay_amount <= 0:
            return
        if self._value == 0:
            self._state["last_decay_ts"] = now
            await self._save_value_to_status_file()
            return
        if self._value > 0:
            self._value = max(0, self._value - decay_amount)
        else:
            self._value = min(0, self._value + decay_amount)
        self._state["value"] = self._value
        self._state["last_decay_ts"] = now
        await self._save_value_to_status_file()

    def _normalize_user_text(self, text: str) -> str:
        t = (text or "").strip().lower()
        t = re.sub(r"\s+", "", t)
        t = re.sub(r"[，。！？!?,.;；、】【【】“”\"'’‘()（）]", "", t)
        if not t:
            return ""
        digest = hashlib.sha256(t.encode("utf-8")).hexdigest()
        return digest[:16]

    def _update_repeat_state(self, user_text_norm: str, now: float):
        last_norm = str(self._state.get("last_user_text_norm", "") or "")
        last_ts = float(self._state.get("repeat_last_ts", 0) or 0)
        if not user_text_norm:
            self._state["repeat_count"] = 0
            self._state["repeat_last_ts"] = now
            self._state["last_user_text_norm"] = ""
            return
        if user_text_norm == last_norm and (now - last_ts) <= self._repeat_window_seconds:
            self._state["repeat_count"] = int(self._state.get("repeat_count", 0) or 0) + 1
        else:
            self._state["repeat_count"] = 1
        self._state["repeat_last_ts"] = now
        self._state["last_user_text_norm"] = user_text_norm

    def _append_recent_event(self, delta: int, now: float):
        events = self._state.get("recent_events", [])
        if not isinstance(events, list):
            events = []
        events.append({"ts": now, "delta": int(delta)})
        cutoff = now - self._recent_window_seconds
        events = [e for e in events if isinstance(e, dict) and float(e.get("ts", 0) or 0) >= cutoff]
        if len(events) > 60:
            events = events[-60:]
        self._state["recent_events"] = events

    def _count_recent(self, now: float) -> tuple[int, int]:
        events = self._state.get("recent_events", [])
        if not isinstance(events, list):
            return 0, 0
        cutoff = now - self._recent_window_seconds
        pos = 0
        neg = 0
        for e in events:
            if not isinstance(e, dict):
                continue
            ts = float(e.get("ts", 0) or 0)
            if ts < cutoff:
                continue
            delta = int(e.get("delta", 0) or 0)
            if delta > 0:
                pos += 1
            elif delta < 0:
                neg += 1
        return pos, neg

    def _update_streaks(self, delta: int):
        if delta > 0:
            self._state["pos_streak"] = int(self._state.get("pos_streak", 0) or 0) + 1
            self._state["neg_streak"] = 0
        elif delta < 0:
            self._state["neg_streak"] = int(self._state.get("neg_streak", 0) or 0) + 1
            self._state["pos_streak"] = 0
        else:
            self._decay_streaks()

    def _decay_streaks(self):
        self._state["pos_streak"] = max(0, int(self._state.get("pos_streak", 0) or 0) - 1)
        self._state["neg_streak"] = max(0, int(self._state.get("neg_streak", 0) or 0) - 1)

    def _apply_relationship_dynamics(self, base_change: int, positive_emotions: int, negative_emotions: int, now: float, user_text: str) -> int:
        if base_change == 0:
            return 0
        ratio = 0.0
        if self._max_value > 0:
            ratio = max(0.0, min(1.0, self._value / self._max_value))

        is_positive = base_change > 0
        is_negative = base_change < 0

        pos_recent, neg_recent = self._count_recent(now)
        repeat_count = int(self._state.get("repeat_count", 0) or 0)

        cooldown_mult = 1.0
        last_change_ts = float(self._state.get("last_change_ts", 0) or 0)
        if last_change_ts > 0 and (now - last_change_ts) < self._cooldown_seconds:
            cooldown_mult = 0.35

        if is_positive:
            pos_level_mult = 1.1 - ratio * 0.6
            pos_level_mult = max(0.35, min(1.2, pos_level_mult))
            pos_diminish = 1.0 / (1.0 + pos_recent / 3.0)
            repeat_mult = 1.0
            if repeat_count >= 2:
                repeat_mult = 0.55
            streak = int(self._state.get("pos_streak", 0) or 0)
            streak_mult = 1.0 + min(0.2, streak * 0.05)
            final_float = base_change * pos_level_mult * pos_diminish * repeat_mult * cooldown_mult * streak_mult
        elif is_negative:
            neg_level_mult = 0.65 + (1.0 - ratio) * 0.7
            neg_level_mult = max(0.6, min(1.6, neg_level_mult))
            neg_diminish = 1.0 / (1.0 + neg_recent / 5.0)
            repeat_mult = 1.0
            if repeat_count >= 2:
                repeat_mult = 1.15
            streak = int(self._state.get("neg_streak", 0) or 0)
            streak_mult = 1.0 + min(0.35, streak * 0.12)
            final_float = base_change * neg_level_mult * neg_diminish * repeat_mult * cooldown_mult * streak_mult
        else:
            return 0

        final_int = int(round(final_float))
        if final_int == 0:
            if abs(final_float) >= 0.6:
                final_int = 1 if final_float > 0 else -1
            else:
                final_int = 0

        return max(-self._max_manner_change, min(self._max_manner_change, final_int))

    def _extract_last_user_text_from_memory(self, memory_content: str, continued_count: int) -> str:
        lines = [ln.strip() for ln in (memory_content or "").split("\n") if ln.strip()]
        if not lines:
            return ""
        count = max(1, continued_count + 1)
        conversations = lines[-max(len(lines), count):]
        for conv in reversed(conversations):
            if ":" not in conv:
                continue
            speaker, content = conv.split(":", 1)
            if speaker.strip() == "user":
                return content.strip()
        for conv in reversed(conversations):
            if ":" not in conv:
                continue
            speaker, content = conv.split(":", 1)
            if speaker.strip() != "bot":
                return content.strip()
        return ""

    def get_manner_value_str(self) -> str:
        """
        获取心动值展示后缀（括号格式）
        :return: 例如（10❤️）或（-3🖤）
        """
        heart = "❤️" if self._value >= 0 else "🖤"
        return f"（{self._value}{heart}）"

    def get_value(self) -> int:
        """
        获取当前好感度值
        :return: 好感度值
        """
        return self._value

    def get_manner_description(self) -> str:
        """
        获取当前好感度状态描述
        :return: 状态描述
        """
        last_description = ""
        for desc in self._manner_descriptions:
            last_description = self._list_to_prompt_str(desc["description"])
            if self._value <= desc["max"]:
                return last_description
        return last_description

    def _ensure_punctuation(self, text: str) -> str:
        """
        确保文本末尾有标点符号
        :param text: 文本
        :return: 添加标点后的文本
        """
        # 定义中英文标点符号
        punctuation = r"[。.，,？?；;]"
        # 如果末尾没有标点符号，则添加一个句号
        if not re.search(punctuation + r"$", text):
            return text + "。"
        return text

    def _list_to_prompt_str(self, content: list | str, prefix: str = "") -> str:
        """
        将列表转换为提示字符串
        :param content: 内容列表或字符串
        :param prefix: 前缀
        :return: 转换后的字符串
        """
        if isinstance(content, list):
            return "".join([prefix + self._ensure_punctuation(item) for item in content])
        else:
            return self._ensure_punctuation(content)

    async def change_manner_value(self, amount: int, now: Optional[float] = None):
        """
        改变好感度值
        :param amount: 变化量
        """
        self._value = max(self._min_value, min(self._max_value, self._value + amount))
        self._state["value"] = self._value
        if now is None:
            now = time.time()
        self._state["last_change_ts"] = now
        await self._save_value_to_status_file()
        logger.info(f"好感度已更新: {self._value} (变化: {amount})")

    async def _save_value_to_status_file(self):
        """
        保存好感度值到存储
        """
        try:
            if not isinstance(self._state, dict) or not self._state:
                self._state = {"version": 1, "value": self._value}
            else:
                self._state["version"] = int(self._state.get("version", 1) or 1)
                self._state["value"] = self._value
            data = json.dumps(self._state, ensure_ascii=False).encode("utf-8")
            await self.plugin.set_plugin_storage(self._status_file, data)
        except Exception as e:
            logger.error(f"保存好感度失败: {e}", exc_info=True)

    async def reset_value(self):
        """
        重置好感度值
        """
        self._value = 0
        self._state["value"] = self._value
        self._state["last_change_ts"] = time.time()
        await self._save_value_to_status_file()
        logger.info("好感度已重置")

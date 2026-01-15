import json
import yaml
import re
import os
import logging
import time
from collections import Counter
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

class TextAnalyzer:
    LOADED_DICTIONARIES = {}
    TEXSMART_BACKOFF_UNTIL = 0.0
    USE_TEXSMART = False

    def __init__(self, plugin):
        self.plugin = plugin

    async def _load_yaml_dict(self, file: str) -> Dict[str, list]:
        """
        Load yaml dictionary file.
        :param file: yaml file path
        """
        if file == "sentiment":
            now = time.time()
            cached = TextAnalyzer.LOADED_DICTIONARIES.get(file)
            cached_ts = float(TextAnalyzer.LOADED_DICTIONARIES.get(f"{file}__ts", 0) or 0)
            if (
                isinstance(cached, dict)
                and (now - cached_ts) < 5
                and "positive_keywords" in cached
                and "negative_keywords" in cached
                and "strong_negative_patterns" in cached
            ):
                return cached
        else:
            if file in TextAnalyzer.LOADED_DICTIONARIES:
                return TextAnalyzer.LOADED_DICTIONARIES[file]

        local_candidates = [
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "config", f"{file}.yaml")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "config", f"{file}.yaml")),
        ]
        for local_path in local_candidates:
            if os.path.exists(local_path):
                try:
                    with open(local_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f) or {}
                    TextAnalyzer.LOADED_DICTIONARIES[file] = data
                    if file == "sentiment":
                        TextAnalyzer.LOADED_DICTIONARIES[f"{file}__ts"] = time.time()
                    return data
                except Exception as e:
                    logger.error(f"读取本地配置文件失败: {local_path}, {e}")

        # 兜底：使用LangBot的配置文件API加载（如果可用）
        config_path = f"assets/config/{file}.yaml"
        try:
            file_bytes = await self.plugin.get_config_file(config_path)
            data = yaml.safe_load(file_bytes) or {}
        except Exception as e:
            logger.error(f"加载配置文件 {config_path} 失败: {e}")
            try:
                config_path = f"config/{file}.yaml"
                file_bytes = await self.plugin.get_config_file(config_path)
                data = yaml.safe_load(file_bytes) or {}
            except Exception as e:
                logger.error(f"尝试从 {config_path} 加载也失败: {e}")
                if file == "sentiment":
                    return {"positive_keywords": [], "negative_keywords": [], "strong_negative_patterns": []}
                data = {file: []}

        TextAnalyzer.LOADED_DICTIONARIES[file] = data
        if file == "sentiment":
            TextAnalyzer.LOADED_DICTIONARIES[f"{file}__ts"] = time.time()
        return data

    def _call_texsmart_api(self, text: str) -> Dict[str, Any]:
        if not TextAnalyzer.USE_TEXSMART:
            return {"error": "disabled"}
        url = "https://texsmart.qq.com/api"
        obj = {"str": text}
        req_str = json.dumps(obj).encode()

        now = time.time()
        if now < TextAnalyzer.TEXSMART_BACKOFF_UNTIL:
            return {"error": "API backoff"}

        try:
            import requests
            r = requests.post(url, data=req_str, timeout=5)
            r.encoding = "utf-8"
            if r.status_code != 200:
                TextAnalyzer.TEXSMART_BACKOFF_UNTIL = now + 300
                logger.warning(f"TexSmart API返回错误状态码: {r.status_code}")
                return {"error": f"API returned status code {r.status_code}"}
            return r.json()
        except requests.Timeout:
            TextAnalyzer.TEXSMART_BACKOFF_UNTIL = now + 120
            logger.warning("TexSmart API调用超时")
            return {"error": "API timeout"}
        except requests.RequestException as e:
            TextAnalyzer.TEXSMART_BACKOFF_UNTIL = now + 120
            logger.warning(f"调用TexSmart API失败: {e}")
            return {"error": "Request failed"}
        except json.JSONDecodeError as e:
            TextAnalyzer.TEXSMART_BACKOFF_UNTIL = now + 120
            logger.warning(f"JSON解析失败: {e}")
            return {"error": "JSON decode failed"}
        except Exception as e:
            TextAnalyzer.TEXSMART_BACKOFF_UNTIL = now + 120
            logger.warning(f"发生意外错误: {e}")
            return {"error": "An unexpected error occurred"}

    def _parse_texsmart_response(self, response):
        parsed_data = {"word_list": [], "phrase_list": [], "entity_list": []}

        # 如果API调用失败，返回空数据
        if "error" in response:
            return parsed_data

        try:
            for word in response.get("word_list", []):
                parsed_data["word_list"].append({"str": word["str"], "tag": word["tag"]})

            for phrase in response.get("phrase_list", []):
                parsed_data["phrase_list"].append({"str": phrase["str"], "tag": phrase["tag"]})

            for entity in response.get("entity_list", []):
                entity_meaning = entity.get("meaning", {})
                # 根据API文档，使用tag_i18n字段而不是type.i18n
                parsed_data["entity_list"].append({
                    "str": entity["str"], 
                    "tag": entity.get("tag", ""), 
                    "i18n": entity.get("tag_i18n", ""), 
                    "related": entity_meaning.get("related", [])
                })
        except KeyError as e:
            logger.error(f"解析TexSmart响应时缺少字段: {e}")
        except Exception as e:
            logger.error(f"解析TexSmart响应失败: {e}")

        return parsed_data

    async def term_freq(self, text: str) -> Tuple[Counter, List[str], List[str]]:
        """
        Calculate word count and retrieve i18n information.
        :param text: text string
        """
        text = await self._remove_meaningless(text)
        words = []
        i18n_list = []
        related_list = []

        words = self._simple_tokenize(text)

        words = self._remove_punctuation(words)  # 删除标点符号项目
        words = self._remove_unless_words(words)  # 删除无意义标签
        i18n_list = self._remove_punctuation(i18n_list)
        related_list = self._remove_punctuation(related_list)

        words = sorted(set(words))
        i18n_list = sorted(set(i18n_list))
        related_list = sorted(set(related_list))

        term_freq_counter = Counter(words)
        return term_freq_counter, i18n_list, related_list

    async def sentiment(self, text: str) -> Dict[str, Any]:
        """
        Calculate the occurrences of each sentiment category words in text.
        :param text: text string
        """
        text = text or ""
        result_dict = {"positive_num": 0, "negative_num": 0}

        sentiment_dict = await self._load_yaml_dict("sentiment")
        positive_cfg = sentiment_dict.get("positive_keywords", [])
        negative_cfg = sentiment_dict.get("negative_keywords", [])
        strong_patterns_cfg = sentiment_dict.get("strong_negative_patterns", [])

        if not positive_cfg and not negative_cfg and not strong_patterns_cfg:
            pos_fallback = await self._load_yaml_dict("positive")
            neg_fallback = await self._load_yaml_dict("negative")
            positive_cfg = pos_fallback.get("positive", [])
            negative_cfg = neg_fallback.get("negative", [])
            strong_patterns_cfg = []

        positive_set = {str(x).strip() for x in (positive_cfg or []) if str(x).strip()}
        negative_set = {str(x).strip() for x in (negative_cfg or []) if str(x).strip()}

        strong_negative_patterns = []
        for pat in (strong_patterns_cfg or []):
            try:
                strong_negative_patterns.append(re.compile(str(pat), re.IGNORECASE))
            except re.error:
                continue

        logger.debug(
            f"sentiment.yaml加载: positive={len(positive_set)}, negative={len(negative_set)}, patterns={len(strong_negative_patterns)}"
        )

        words = self._simple_tokenize(text) + text.split()

        # 移除分词中标点符号项目
        words = self._remove_punctuation(words)

        word_num = len(words)

        pos_hits = set()
        neg_hits = set()

        output = {"positive": [], "negative": [], "unrecognized": []}

        # 基于分词的匹配
        for word in words:
            if any(neg_word in word for neg_word in negative_set):
                neg_hits.add(word)
                continue

            if word.startswith("不") and any(pos_word in word for pos_word in positive_set):
                neg_hits.add(word)
                continue

            if any(pos_word in word for pos_word in positive_set):
                pos_hits.add(word)
                continue

            output["unrecognized"].append(word)

        # 原文本直接匹配（兜底，保证中文无空格时仍能识别）
        raw = text
        for pos_word in positive_set:
            neg_form = f"不{pos_word}"
            if neg_form in raw:
                neg_hits.add(neg_form)
        for neg_word in negative_set:
            if neg_word and neg_word in raw:
                neg_hits.add(neg_word)
        for pos_word in positive_set:
            if pos_word and pos_word in raw and f"不{pos_word}" not in raw:
                pos_hits.add(pos_word)

        for pos_word in positive_set:
            neg_form = f"不{pos_word}"
            if neg_form in raw:
                pos_hits = {h for h in pos_hits if pos_word not in h}

        for i, pat in enumerate(strong_negative_patterns):
            if pat.search(raw):
                neg_hits.add(f"strong_profanity_{i}")
                neg_hits.add(f"strong_profanity_{i}_2")

        result_dict["positive_num"] = len(pos_hits)
        result_dict["negative_num"] = len(neg_hits)

        output["positive"] = sorted(pos_hits)
        output["negative"] = sorted(neg_hits)
        output["unrecognized"] = sorted(set(output["unrecognized"]))
        logger.debug(f"情感分析结果: {output}")

        result_dict["word_num"] = word_num

        await self._save_unrecognized_words(output["unrecognized"])

        return result_dict

    def _simple_tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens: List[str] = []
        tokens.extend(re.findall(r"[\u4e00-\u9fff]{2,}", text))
        tokens.extend(re.findall(r"[A-Za-z0-9]{2,}", text))
        return tokens

    def _remove_punctuation(self, words: List[str]) -> List[str]:
        """
        Remove all punctuation from the list of words.
        :param words: list of words
        :return: list of words without punctuation
        """
        punct_pattern = re.compile(r"[^\w]", re.UNICODE)
        return [word for word in words if not punct_pattern.search(word)]

    async def _save_unrecognized_words(self, words: List[str]):
        """
        Save unrecognized words to a YAML file after sorting and removing duplicates.
        :param words: List of unrecognized words
        """
        existing_words = []
        
        try:
            # 尝试加载已存在的未识别单词
            unrecognized_dict = await self._load_yaml_dict("unrecognized_words")
            existing_words = unrecognized_dict.get("unrecognized", [])
        except Exception as e:
            logger.error(f"加载未识别单词文件失败: {e}")

        # 合并现有单词与新单词，去重并排序
        combined_words = sorted(set(existing_words + words))

        try:
            # 保存到插件存储
            import yaml
            data = yaml.dump({"unrecognized": combined_words}, allow_unicode=True)
            await self.plugin.set_plugin_storage("unrecognized_words", data.encode("utf-8"))
        except Exception as e:
            logger.error(f"保存未识别单词失败: {e}")

    async def _remove_meaningless(self, text: str) -> str:
        """
        Remove meaningless words and punctuation from the text.
        :param text: input text
        """
        meaningless_dict = await self._load_yaml_dict("meaningless")
        meaningless = meaningless_dict.get("meaningless", [])

        for word in meaningless:
            text = text.replace(word, "")

        return text

    def _remove_unless_words(self, items: List[str]) -> List[str]:
        """
        Remove items that are only a single character long or match unwanted patterns.
        :param items: list of strings
        :return: list of strings with unwanted items removed
        """
        unwanted_patterns = [r"^\d+$", r"\d+年", r"\d+月", r"\d+日", r"\d+分"]

        def is_unwanted(item):
            return any(re.search(pattern, item) for pattern in unwanted_patterns)

        return [item for item in items if len(item) > 1 and not is_unwanted(item)]

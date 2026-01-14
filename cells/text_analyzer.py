import json
import requests
import yaml
import re
import os
import logging
from collections import Counter
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

class TextAnalyzer:
    LOADED_DICTIONARIES = {}

    def __init__(self, plugin):
        self.plugin = plugin

    async def _load_yaml_dict(self, file: str) -> Dict[str, list]:
        """
        Load yaml dictionary file.
        :param file: yaml file path
        """
        # 如果字典已经加载过，则直接返回
        if file in TextAnalyzer.LOADED_DICTIONARIES:
            return TextAnalyzer.LOADED_DICTIONARIES[file]

        # 尝试从插件配置文件目录加载
        config_path = f"assets/config/{file}.yaml"
        try:
            # 使用LangBot的配置文件API加载
            file_bytes = await self.plugin.get_config_file(config_path)
            data = yaml.safe_load(file_bytes)
        except Exception as e:
            logger.error(f"加载配置文件 {config_path} 失败: {e}")
            # 尝试从不同路径加载
            try:
                config_path = f"config/{file}.yaml"
                file_bytes = await self.plugin.get_config_file(config_path)
                data = yaml.safe_load(file_bytes)
            except Exception as e:
                logger.error(f"尝试从 {config_path} 加载也失败: {e}")
                # 如果都失败，使用默认值
                data = {file: []}

        # 将加载的字典数据存入全局变量
        TextAnalyzer.LOADED_DICTIONARIES[file] = data
        return data

    def _call_texsmart_api(self, text: str) -> Dict[str, Any]:
        url = "https://texsmart.qq.com/api"
        obj = {"str": text}
        req_str = json.dumps(obj).encode()

        try:
            r = requests.post(url, data=req_str, timeout=5)
            r.encoding = "utf-8"
            if r.status_code != 200:
                logger.error(f"TexSmart API返回错误状态码: {r.status_code}")
                return {"error": f"API returned status code {r.status_code}"}
            return r.json()
        except requests.Timeout:
            logger.error("TexSmart API调用超时")
            return {"error": "API timeout"}
        except requests.RequestException as e:
            logger.error(f"调用TexSmart API失败: {e}")
            return {"error": "Request failed"}
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            return {"error": "JSON decode failed"}
        except Exception as e:
            logger.error(f"发生意外错误: {e}")
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

        response = self._call_texsmart_api(text)
        parsed_data = self._parse_texsmart_response(response)

        # 如果API调用失败，使用简单的分词方法
        if not parsed_data["word_list"]:
            logger.info("TexSmart API调用失败，使用简单分词")
            # 使用简单的空格分词作为备选方案
            words = text.split()
        else:
            words = [w["str"] for w in parsed_data["word_list"]]  # 基础粒度分词
            for entity in parsed_data["entity_list"]:
                i18n_list.append(entity["i18n"])  # 实体类型标注
                related_list.extend(entity["related"])  # 实体的语义联想

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
        text = await self._remove_meaningless(text)
        result_dict = {"positive_num": 0, "negative_num": 0}

        positive_dict = await self._load_yaml_dict("positive")
        positive_list = positive_dict.get("positive", [])
        negative_dict = await self._load_yaml_dict("negative")
        negative_list = negative_dict.get("negative", [])

        response = self._call_texsmart_api(text)
        parsed_data = self._parse_texsmart_response(response)

        # 如果API调用失败或没有获取到短语列表，使用简单的分词方法
        if not parsed_data["phrase_list"]:
            logger.info("TexSmart API调用失败或没有短语列表，使用简单分词")
            # 使用简单的空格分词作为备选方案
            words = text.split()
        else:
            words = [w["str"] for w in parsed_data["phrase_list"]]

        # 移除分词中标点符号项目
        words = self._remove_punctuation(words)

        word_num = len(words)
        output = {"positive": [], "negative": [], "unrecognized": []}

        for word in words:
            if word in positive_list:
                result_dict["positive_num"] += 1
                output["positive"].append(word)
            elif any(neg_word in word for neg_word in negative_list):
                result_dict["negative_num"] += 1
                output["negative"].append(word)
            else:
                output["unrecognized"].append(word)

        output["unrecognized"] = sorted(set(output["unrecognized"]))
        logger.debug(f"情感分析结果: {output}")

        result_dict["word_num"] = word_num

        await self._save_unrecognized_words(output["unrecognized"])

        return result_dict

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

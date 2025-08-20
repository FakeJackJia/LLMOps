import re
from typing import Callable
from injector import inject
from dataclasses import dataclass
from internal.model import ProcessRule
from langchain.text_splitter import TextSplitter, RecursiveCharacterTextSplitter

@inject
@dataclass
class ProcessRuleService:
    """处理规则服务"""

    @classmethod
    def get_text_splitter_by_process_rule(
            cls,
            process_rule: ProcessRule,
            length_function: Callable[[str], int] = len,
            **kwargs
    ) -> TextSplitter:
        """根据传递的处理规则+长度计算函数, 获取相应的文本分割器"""
        return RecursiveCharacterTextSplitter(
            chunk_size=process_rule.rule["segment"]["chunk_size"],
            chunk_overlap=process_rule.rule["segment"]["chunk_overlap"],
            separators=process_rule.rule["segment"]["separators"],
            is_separator_regex=True,
            length_function=length_function,
            **kwargs
        )

    @classmethod
    def clean_text_by_process_rule(cls, text: str, process_rule: ProcessRule) -> str:
        """根据传递的处理规则清楚多余的字符串"""
        for pre_process_rule in process_rule.rule["pre_process_rules"]:
            if pre_process_rule["id"] == "remove_extra_space" and pre_process_rule["enabled"]:
                pattern = r'\n{3,}'
                text = re.sub(pattern, '\n\n', text)
                pattern = r'[\t\f\r\x20\u00a0\u1680\u180e\u2000-\u200a\u202f\u205f\u3000]{2,}'
                text = re.sub(pattern, ' ', text)
            if pre_process_rule["id"] == "remove_url_and_email" and pre_process_rule["enabled"]:
                pattern = r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
                text = re.sub(pattern, '', text)
                pattern = r'https?://[^\s]+'
                text = re.sub(pattern, '', text)
        return text
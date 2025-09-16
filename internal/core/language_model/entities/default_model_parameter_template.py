from .model_entity import DefaultModelParameterName, ModelParameterType


# 默认模型参数模板, 用于检索YAML配置, 以OpenAI的模型接口为标准
DEFAULT_MODEL_PARAMETER_TEMPLATE = {
    # 温度模板默认参数
    DefaultModelParameterName.TEMPERATURE: {
        "label": "温度",
        "type": ModelParameterType.FLOAT,
        "help": "温度控制随机性, 较低的温度会导致较少的随机生成, 随着温度接近零, 模型将变得更确定, 较高的温度会导致更多随机内容被生成",
        "required": False,
        "default": 1,
        "min": 0,
        "max": 2,
        "precision": 2,
        "options": [],
    },
    # TopP核采样
    DefaultModelParameterName.TOP_P: {
        "label": "Top P",
        "type": ModelParameterType.FLOAT,
        "help": "通过核心采样控制多样性, 0.5表示考虑了一半的所有可能性加权选项",
        "required": False,
        "default": 0.2,
        "min": 0.1,
        "max": 1,
        "precision": 2,
        "options": [],
    },
    # 存在惩罚
    DefaultModelParameterName.PRESENCE_PENALTY: {
        "label": "存在惩罚",
        "type": ModelParameterType.FLOAT,
        "help": "对文本中已有的标记的对数概率施加惩罚",
        "required": False,
        "default": 0,
        "min": -2.0,
        "max": 2.0,
        "precision": 2,
        "options": [],
    },
    # 频率惩罚
    DefaultModelParameterName.FREQUENCY_PENALTY: {
        "label": "频率惩罚",
        "type": ModelParameterType.FLOAT,
        "help": "对文本中已有的标记的对数概率施加惩罚",
        "required": False,
        "default": 0,
        "min": -2.0,
        "max": 2.0,
        "precision": 2,
        "options": [],
    }
}
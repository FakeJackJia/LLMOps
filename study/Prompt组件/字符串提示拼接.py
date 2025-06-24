
from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template("请说一个关于{subject}的笑话") + ", 让我开心" + "\n"

print(prompt.invoke({"subject":"123"}).to_string())

from langchain_core.prompts import ChatPromptTemplate

chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是OpenAI机器人"),
])

human_chat_prompt = ChatPromptTemplate.from_messages([
    ("human", "{query}")
])

chat_prompt = chat_prompt + human_chat_prompt
print(chat_prompt.invoke({"query":"你是谁"}))


full_template = PromptTemplate.from_template("""
{instruction}

{example}

{start}""")

from langchain_core.prompts import PipelinePromptTemplate

instruction_prompt = PromptTemplate.from_template("你正在模拟{person}")
example_prompt = PromptTemplate.from_template("""下面是个例子:
Q: {example_q}
A: {example_a}""")
start_prompt = PromptTemplate.from_template("现在请回答问题 Q: {input} A:")

pipeline_prompt = [
    ("instruction", instruction_prompt),
    ("example", example_prompt),
    ("start", start_prompt),
]

pipeline_p = PipelinePromptTemplate(
    final_prompt=full_template,
    pipeline_prompts=pipeline_prompt,
)

print(pipeline_p.invoke({
    "person": "雷军",
    "example_q": "你最喜欢的汽车是什么",
    "example_a": "小米",
    "input": "你最喜欢的手机是什么"
}).to_string())

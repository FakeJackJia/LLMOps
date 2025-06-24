import datetime

from langchain_core.prompts import (
    PromptTemplate,
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
)

from langchain_core.messages import AIMessage


prompt = PromptTemplate.from_template("请将一个关于{subject}的冷笑话")
print(prompt.format(subject="123"))
prompt_value = prompt.invoke({"subject":"123"})
print(prompt_value.to_string())
print(prompt_value.to_messages())

chat_prompt = ChatPromptTemplate.from_messages([
    ("system", "你是OpenAI开发的机器人, 当前的时间为:{now}"),
    MessagesPlaceholder("chat_history"), # 有时候可能还有其他消息 但不确定
    HumanMessagePromptTemplate.from_template("请将一个关于{subject}的冷笑话"),
]).partial(now=datetime.datetime.now())

print("===================")

chat_prompt_value = chat_prompt.invoke({
    "chat_history": [
        ("human", "我叫Jack"),
        AIMessage("你好, 我是ChatGPT, 有什么可以帮你"),
    ],
    "subject": "123",
})

print(chat_prompt_value.to_string())
print(chat_prompt_value.to_messages())
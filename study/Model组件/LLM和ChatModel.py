from datetime import datetime

import dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

dotenv.load_dotenv()


prompt = ChatPromptTemplate.from_messages([
    ("system", "你是OpenAI聊天机器人, 现在时间是{now}"),
    ("human", "{query}"),
]).partial(now=datetime.now())

llm = ChatOpenAI(model="gpt-3.5-turbo-16k")

resp = llm.invoke(prompt.invoke({"query":"现在是几点"}))
print(resp.type)
print(resp.content)
print(resp.response_metadata)

print("===============================")

resp = llm.batch([prompt.invoke({"query":"你好, 你是？"}), prompt.invoke({"query":"现在是几点?"})])
for r in resp:
    print(r.content)

print("==============================")

resp = llm.stream(prompt.invoke({"query":"你能介绍下LLMOps吗"}))
for r in resp:
    print(r.content, flush=True, end="")
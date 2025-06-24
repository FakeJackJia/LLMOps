
import dotenv
from operator import itemgetter
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableParallel, RunnablePassthrough

dotenv.load_dotenv()

joke = ChatPromptTemplate.from_template("请将一个关于{subject}的冷笑话, 尽可能短一些")
poem = ChatPromptTemplate.from_template("请写一个关于{subject}的诗, 尽可能短一些")

llm = ChatOpenAI(model='gpt-3.5-turbo-16k')

parser = StrOutputParser()

joke_chain = joke | llm | parser
poem_chain = poem | llm | parser

map_chain = RunnableParallel(joke=joke_chain, poem=poem_chain)

# map_chain = RunnableParallel({
#     "joke": joke_chain,
#     "poem": poem_chain,
# })

res = map_chain.invoke({"subject": "程序员"})
print(res)

print("==========================")

def retrieval(query: str) -> str:
    """一个模拟的检索器函数"""
    print("正在检索:", query)
    return "我是Jack"

prompt = ChatPromptTemplate.from_template("""请根据用户的问题回答, 可以参考对应的上下文进行生成.

<context>
{context}
<context>

用户的提问是: {query}""")

chain = {
            "context": lambda x: retrieval(x["query"]),
            "query": itemgetter("query"),
        } | prompt | llm | parser

content = chain.invoke({"query": "你好我是谁?"})
print(content)

print("==============================")

chain = {
            "context": retrieval,
            # RunnablePassthrough() would keep the original input from last step
            "query": RunnablePassthrough(),
        } | prompt | llm | parser

content = chain.invoke("你好我是谁?")
print(content)

# If pass as dict, we can use RunnablePassthrough.assign() to add new variable
chain = RunnablePassthrough.assign(context=lambda x: retrieval(x["query"])) | prompt | llm | parser
content = chain.invoke({"query": "你好我是谁?"})
print(content)
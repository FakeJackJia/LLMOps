
import dotenv
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field

dotenv.load_dotenv()

prompt = ChatPromptTemplate.from_template("{query}")

llm = ChatOpenAI(model="gpt-3.5-turbo-16k")

parser = StrOutputParser()
content = parser.parse("你好")
print(content)

res = parser.invoke(llm.invoke(prompt.invoke({"query":"你好, 你是?"})))
print(res)

print("======================")
class Joke(BaseModel):
    joke: str = Field(description="回答用户的冷笑话")
    punchline: str = Field(description="这个笑点")

parser = JsonOutputParser(pydantic_object=Joke)
print(parser.get_format_instructions())

prompt = ChatPromptTemplate.from_template("请根据用户提问进行回答\n {format_instruction}\n{query}").partial(
    format_instruction=parser.get_format_instructions())

res = parser.invoke(llm.invoke(prompt.invoke({"query":"请将一个关于程序员的冷笑话"})))
print(res)
from typing import Dict, Any, List, Optional
from uuid import UUID

import dotenv
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.callbacks import StdOutCallbackHandler, BaseCallbackHandler

dotenv.load_dotenv()

class LLMOpsCallbackHandler(BaseCallbackHandler):
    """自定义LLMOps回调处理器"""

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Any:
        print("聊天模型开始执行了")
        print("serialized: ", serialized)
        print("messages: ", messages)

prompt = ChatPromptTemplate.from_template("{query}")

llm = ChatOpenAI(model='gpt-3.5-turbo-16k')

chain = {"query": RunnablePassthrough()} | prompt | llm | StrOutputParser()

content = chain.invoke("你好, 你是?",
                       config={"callbacks": [StdOutCallbackHandler(), LLMOpsCallbackHandler()]})
print(content)
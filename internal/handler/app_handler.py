import json
import uuid
from threading import Thread
from typing import Dict, Any, Literal, Generator
from queue import Queue

from internal.schema import CompletionReq
from pkg.response import success_json, validate_error_json, success_message, compact_generate_response
from internal.exception import FailException
from internal.service import (
    AppService,
    VectorDatabaseService,
    ApiToolService,
    ConversationService,
)
from internal.task.demo_task import demo_task
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager

from dataclasses import dataclass
from injector import inject
from uuid import UUID
from operator import itemgetter

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain.memory import ConversationBufferWindowMemory
from langchain_community.chat_message_histories import FileChatMessageHistory
from langchain_core.runnables import RunnableLambda, RunnablePassthrough, RunnableConfig
from langchain_core.memory import BaseMemory
from langchain_core.tracers import Run
from langgraph.graph import MessagesState, END, StateGraph
from langchain_core.messages import ToolMessage


@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    vector_database_service: VectorDatabaseService
    api_tool_service: ApiToolService
    builtin_provider_manager: BuiltinProviderManager
    conversation_service: ConversationService

    def create_app(self):
        """调用服务创建的APP记录"""
        app = self.app_service.create_app()

        return success_message(f"应用成功创建, id为{app.id}")

    def get_app(self, id: UUID):
        app = self.app_service.get_app(id)

        return success_message(f"应用已经成功获取, 名字是{app.name}")

    def update_app(self, id: UUID):
        app = self.app_service.update_app(id)

        return success_message(f"应用已经成功修改, 修改的名字是{app.name}")

    def delete_app(self, id: UUID):
        app = self.app_service.delete_app(id)

        return success_message(f"应用已经成功删除, id为:{app.id}")

    @classmethod
    def _load_memory_variables(cls, input: Dict[str, Any], config: RunnableConfig) -> Dict[str, Any]:
        """加载记忆变量信息"""
        # 从config中获取configurable
        configurable = config.get("configurable", {})
        configurable_memory = configurable.get("memory", None)

        if configurable_memory is not None and isinstance(configurable_memory, BaseMemory):
            return configurable_memory.load_memory_variables(input)

        return {"history": []}

    @classmethod
    def _save_context(cls, run_obj: Run, config: RunnableConfig) -> None:
        """存储对应的上下文信息到记忆实体中"""
        configurable = config.get("configurable", {})
        configurable_memory = configurable.get("memory", None)

        if configurable_memory is not None and isinstance(configurable_memory, BaseMemory):
            configurable_memory.save_context(run_obj.inputs, run_obj.outputs)

    def debug(self, app_id: UUID):
        """应用会话调试聊天接口, 该接口为流式事件输出"""
        req = CompletionReq()
        if not req.validate():
            return validate_error_json(req.errors)

        # 创建队列并提取query数据
        q = Queue()
        query = req.query.data

        # 创建graph图程序应用
        def graph_app() -> None:
            """创建Graph图程序应用并执行"""
            # 创建tools工具列表
            tools = [
                self.builtin_provider_manager.get_tool("google", "google_serper")(),
                self.builtin_provider_manager.get_tool("gaode", "gaode_weather")(),
                self.builtin_provider_manager.get_tool("dalle", "dalle3")(),
            ]

            # 定义大语言模型/聊天机器人节点
            def chatbot(state: MessagesState) -> MessagesState:
                """聊天机器人节点"""
                llm = ChatOpenAI(model='gpt-4o-mini', temperature=0.7).bind_tools(tools)

                # 调用stream函数获取流式输出内容, 并判断生成内容是文本还是工具调用参数
                is_first_chunk = True
                is_tool_call = False
                gathered = None
                id = str(uuid.uuid4())
                for chunk in llm.stream(state["messages"]):
                    # 检测是不是第一个块, 部分LLM的第一个块不会生成内容, 需要抛弃
                    if is_first_chunk and chunk.content == "" and not chunk.tool_calls:
                        continue

                    # 叠加相应的区块
                    if is_first_chunk:
                        gathered = chunk
                        is_first_chunk = False
                    else:
                        gathered += chunk

                    # 判断是工具调用还是文本生成, 往队列中添加不同的数据
                    if chunk.tool_calls or is_tool_call:
                        is_tool_call = True
                        q.put({
                            "id": id,
                            "event": "agent_thought",
                            "data": json.dumps(chunk.tool_call_chunks),
                        })
                    else:
                        q.put({
                            "id": id,
                            "event": "agent_message",
                            "data": chunk.content
                        })
                return {"messages": [gathered]}

            # 定义工具调用节点
            def tool_executor(state: MessagesState) -> MessagesState:
                """工具执行节点"""
                tool_calls = state["messages"][-1].tool_calls

                tools_by_name = {tool.name: tool for tool in tools}

                messages = []
                for tool_call in tool_calls:
                    id = str(uuid.uuid4())
                    tool = tools_by_name[tool_call["name"]]
                    tool_result = tool.invoke(tool_call["args"])
                    messages.append(ToolMessage(
                        tool_call_id=tool_call["id"],
                        content=json.dumps(tool_result),
                        name=tool_call["name"],
                    ))
                    q.put({
                        "id": id,
                        "event": "agent_action",
                        "data": json.dumps(tool_result),
                    })
                return {"messages": messages}

            # 定义路由函数
            def route(state: MessagesState) -> Literal["tool_executor", "__end__"]:
                """定义路由节点, 用于确认下一步骤"""
                ai_message = state["messages"][-1]
                if hasattr(ai_message, "tool_calls") and len(ai_message.tool_calls) > 0:
                    return "tool_executor"
                return END

            # 创建状态图
            graph_builder = StateGraph(MessagesState)

            # 添加节点
            graph_builder.add_node("llm", chatbot)
            graph_builder.add_node("tool_executor", tool_executor)

            # 添加边
            graph_builder.set_entry_point("llm")
            graph_builder.add_conditional_edges("llm", route)
            graph_builder.add_edge("tool_executor", "llm")

            graph = graph_builder.compile()

            result = graph.invoke({"messages": [("human", query)]})
            print(result)
            q.put(None)

        def stream_event_response() -> Generator:
            """流式事件输出响应"""
            while True:
                item = q.get()
                if item is None:
                    break

                yield f"event: {item.get('event')}\ndata: {json.dumps(item)}\n\n"
                q.task_done()

        t = Thread(target=graph_app)
        t.start()

        return compact_generate_response(stream_event_response())


    def _debug(self, app_id: UUID):
        """聊天接口"""
        # 1. 提取从接口中获取的输入
        req = CompletionReq()
        if not req.validate():
            return validate_error_json(req.errors)

        # 2. 创建prompt与记忆
        system_prompt = """你是一个强大的聊天机器人, 能根据对应的上下文和历史对话信息回复用户的提问. \n\n
        <context>{context}</context>"""
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder('history'),
            ("human", "{query}")
        ])
        memory = ConversationBufferWindowMemory(
            k=3,
            input_key="query",
            output_key="output",
            return_messages=True,
            chat_memory=FileChatMessageHistory('./storage/memory/chat_history.txt')
        )

        # 3.创建llm
        llm = ChatOpenAI(model="gpt-3.5-turbo-16k")

        # 4. 创建链应用
        retriever = self.vector_database_service.get_retriever() | self.vector_database_service.combine_documents
        chain = (RunnablePassthrough.assign(
            history=RunnableLambda(self._load_memory_variables) | itemgetter('history'),
            context=itemgetter("query") | retriever
        ) | prompt | llm | StrOutputParser()).with_listeners(on_end=self._save_context)

        # 5. 调用链得到结果
        chain_input = {"query": req.query.data}
        content = chain.invoke(chain_input, config={'configurable': {'memory': memory}})

        return success_json({"content": content})

    def ping(self):
        human_message = "你好 我叫Jack 你是?"
        ai_message = "你好 我是ChatGPT"
        old_summary = "人类询问AI关于LLM（大型语言模型）的介绍，AI提供了LLM的定义、工作原理、功能与应用、优点和局限性，并表示如果需要，可以绘制一张LLM工作原理的简图以帮助理解。"
        summary = self.conversation_service.summary(human_message, ai_message, old_summary)
        return success_json({"summary": summary})
        #raise FailException("数据未找到")
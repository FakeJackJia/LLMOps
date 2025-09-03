import json
import time
import uuid
from threading import Thread
from typing import Literal, Generator
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    SystemMessage,
    RemoveMessage,
    ToolMessage,
    messages_to_dict,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, END
from .base_agent import BaseAgent
from internal.core.agent.entities.agent_entity import AgentState, DATASET_RETRIEVAL_TOOL_NAME
from internal.core.agent.entities.queue_entity import AgentQueueEvent, QueueEvent
from internal.exception import FailException

class FunctionCallAgent(BaseAgent):
    """基于函数/工具调用的智能体"""

    def run(
            self,
            query: str,
            history: list[AnyMessage] = None,
            long_term_memory: str = ""
    ) -> Generator[AgentQueueEvent, None, None]:
        """运行智能体应用, 并使用yield关键字返回对应的数据"""
        if history is None:
            history = []

        agent = self.build_graph()

        thread = Thread(target=agent.invoke, args=({
            "messages": [HumanMessage(content=query)],
            "history": history,
            "long_term_memory": long_term_memory,
        },))
        thread.start()

        yield from self.agent_queue_manager.listen()

    def build_graph(self) -> CompiledStateGraph:
        """构建LangGraph图结构构建"""
        graph = StateGraph(AgentState)

        graph.add_node("long_term_memory_recall", self._long_term_memory_recall_node)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tools", self._tools_node)

        graph.set_entry_point("long_term_memory_recall")
        graph.add_edge("long_term_memory_recall", "llm")
        graph.add_conditional_edges("llm", self._tools_condition)
        graph.add_edge("tools", "llm")

        agent = graph.compile()
        return agent

    def _long_term_memory_recall_node(self, state: AgentState) -> AgentState:
        """长期记忆召回节点"""
        long_term_memory = ""
        if self.agent_config.enable_long_term_memory:
            long_term_memory = state["long_term_memory"]
            self.agent_queue_manager.publish(AgentQueueEvent(
                id=uuid.uuid4(),
                task_id=self.agent_queue_manager.task_id,
                event=QueueEvent.LONG_TERM_MEMORY_RECALL,
                observation=long_term_memory,
            ))

        preset_messages = [
            SystemMessage(self.agent_config.system_prompt.format(
                preset_prompt=self.agent_config.preset_prompt,
                long_term_memory=long_term_memory,
            ))
        ]

        # 短期历史消息
        history = state["history"]
        if isinstance(history, list) and len(history) > 0:
            # [人类消息, AI消息, ...]
            if len(history) % 2 != 0:
                raise FailException("智能体历史消息列表格式错误")

            preset_messages.extend(history)

        human_message= state["messages"][-1]
        preset_messages.append(HumanMessage(content=human_message.content))

        return {
            "messages": [RemoveMessage(id=human_message.id), *preset_messages]
        }

    def _llm_node(self, state: AgentState) -> AgentState:
        """大语言模型节点"""
        id = uuid.uuid4()
        start_at = time.perf_counter()
        llm = self.agent_config.llm

        if hasattr(llm, "bind_tools") and callable(getattr(llm, "bind_tools")) and len(self.agent_config.tools) > 0:
            llm = llm.bind_tools(self.agent_config.tools)

        gathered = None
        is_first_chunk = True
        generation_type = ""
        for chunk in llm.stream(state["messages"]):
            if is_first_chunk:
                gathered = chunk
                is_first_chunk = False
            else:
                gathered += chunk

            if not generation_type:
                if chunk.tool_calls:
                    generation_type = "thought"
                elif chunk.content:
                    generation_type = "message"

            if generation_type == "message":
                self.agent_queue_manager.publish(AgentQueueEvent(
                    id=id,
                    task_id=self.agent_queue_manager.task_id,
                    event=QueueEvent.AGENT_MESSAGE,
                    thought=chunk.content,
                    message=messages_to_dict(state["messages"]),
                    answer=chunk.content,
                    latency=(time.perf_counter() - start_at),
                ))

        if generation_type == "thought":
            self.agent_queue_manager.publish(AgentQueueEvent(
                id=id,
                task_id=self.agent_queue_manager.task_id,
                event=QueueEvent.AGENT_THOUGHT,
                thought=json.dumps(gathered.tool_calls),
                message=messages_to_dict(state["messages"]),
                latency=(time.perf_counter() - start_at),
            ))
        elif generation_type == "message":
            self.agent_queue_manager.stop_listen()

        return {"messages": [gathered]}

    def _tools_node(self, state: AgentState) -> AgentState:
        """工具执行节点"""
        tools_by_name = {tool.name: tool for tool in self.agent_config.tools}

        tool_calls = state["messages"][-1].tool_calls

        messages = []
        for tool_call in tool_calls:
            id = uuid.uuid4()
            start_at = time.perf_counter()

            tool = tools_by_name[tool_call["name"]]
            tool_result = tool.invoke(tool_call["args"])

            messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=json.dumps(tool_result),
                name=tool_call["name"],
            ))

            event = QueueEvent.AGENT_ACTION if tool_call["name"] != DATASET_RETRIEVAL_TOOL_NAME else QueueEvent.DATASET_RETRIEVAL

            self.agent_queue_manager.publish(AgentQueueEvent(
                id=id,
                task_id=self.agent_queue_manager.task_id,
                event=event,
                observation=json.dumps(tool_result),
                tool=tool_call["name"],
                tool_input=tool_call["args"],
                latency=time.perf_counter() - start_at,
            ))

        return {"messages": messages}

    @classmethod
    def _tools_condition(cls, state: AgentState) -> Literal["tools", "__end__"]:
        """检测下一步是执行tools还是结束"""
        message = state["messages"][-1]

        if hasattr(message, "tool_calls") and len(message.tool_calls) > 0:
            return "tools"

        return END
import json
import logging
import re
import time
import uuid
from typing import Literal
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    RemoveMessage,
    ToolMessage,
    messages_to_dict,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, END
from .base_agent import BaseAgent
from internal.core.agent.entities.agent_entity import (
    AgentState,
    DATASET_RETRIEVAL_TOOL_NAME,
    MAX_ITERATION_RESPONSE,
)
from internal.core.agent.entities.queue_entity import AgentThought, QueueEvent

class FunctionCallAgent(BaseAgent):
    """基于函数/工具调用的智能体"""

    def _build_agent(self) -> CompiledStateGraph:
        """构建LangGraph图结构构建"""
        graph = StateGraph(AgentState)

        graph.add_node("preset_operation", self._preset_operation_node)
        graph.add_node("long_term_memory_recall", self._long_term_memory_recall_node)
        graph.add_node("llm", self._llm_node)
        graph.add_node("tools", self._tools_node)

        graph.set_entry_point("preset_operation")
        graph.add_conditional_edges("preset_operation", self._preset_operation_condition)
        graph.add_edge("long_term_memory_recall", "llm")
        graph.add_conditional_edges("llm", self._tools_condition)
        graph.add_edge("tools", "llm")

        agent = graph.compile()
        return agent

    def _preset_operation_node(self, state: AgentState) -> AgentState:
        """预设操作, 涵盖: 输入审核、数据预处理、条件边等"""
        review_config = self.agent_config.review_config
        query = state["messages"][-1].content

        if review_config["enable"] and review_config["inputs_config"]["enable"]:
            contains_keyword = any(keyword in query for keyword in review_config["keywords"])
            if contains_keyword:
                preset_response = review_config["inputs_config"]["preset_response"]
                self.agent_queue_manager.publish(state["task_id"], AgentThought(
                    id=uuid.uuid4(),
                    task_id=state["task_id"],
                    event=QueueEvent.AGENT_MESSAGE,
                    thought=preset_response,
                    message=messages_to_dict(state["messages"]),
                    answer=preset_response,
                    latency=0
                ))
                self.agent_queue_manager.publish(state["task_id"], AgentThought(
                    id=uuid.uuid4(),
                    task_id=state["task_id"],
                    event=QueueEvent.AGENT_END,
                ))
                return {"messages": [AIMessage(preset_response)]}

        return {"messages": []}

    def _long_term_memory_recall_node(self, state: AgentState) -> AgentState:
        """长期记忆召回节点"""
        long_term_memory = ""
        if self.agent_config.enable_long_term_memory:
            long_term_memory = state["long_term_memory"]
            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=uuid.uuid4(),
                task_id=state["task_id"],
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
                self.agent_queue_manager.publish_error(state["task_id"], "智能体历史消息列表格式错误")
                logging.exception(f"智能体历史消息列表格式错误")

            preset_messages.extend(history)

        human_message= state["messages"][-1]
        preset_messages.append(HumanMessage(content=human_message.content))

        return {
            "messages": [RemoveMessage(id=human_message.id), *preset_messages]
        }

    def _llm_node(self, state: AgentState) -> AgentState:
        """大语言模型节点"""
        if state["iteration_count"] > self.agent_config.max_iteration_count:
            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=uuid.uuid4(),
                task_id=state["task_id"],
                event=QueueEvent.AGENT_MESSAGE,
                thought=MAX_ITERATION_RESPONSE,
                message=messages_to_dict(state["messages"]),
                answer=MAX_ITERATION_RESPONSE,
                latency=0,
            ))
            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=uuid.uuid4(),
                task_id=state["task_id"],
                event=QueueEvent.AGENT_END,
            ))

            return {"messages": [AIMessage(MAX_ITERATION_RESPONSE)]}

        id = uuid.uuid4()
        start_at = time.perf_counter()
        llm = self.llm

        if hasattr(llm, "bind_tools") and callable(getattr(llm, "bind_tools")) and len(self.agent_config.tools) > 0:
            llm = llm.bind_tools(self.agent_config.tools)

        gathered = None
        is_first_chunk = True
        generation_type = ""
        try:
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
                    review_config = self.agent_config.review_config
                    content = chunk.content

                    if review_config["enable"] and review_config["outputs_config"]["enable"]:
                        for keyword in review_config["keywords"]:
                            content = re.sub(re.escape(keyword), "**", content, flags=re.IGNORECASE)

                    self.agent_queue_manager.publish(state["task_id"], AgentThought(
                        id=id,
                        task_id=state["task_id"],
                        event=QueueEvent.AGENT_MESSAGE,
                        thought=content,
                        message=messages_to_dict(state["messages"]),
                        answer=content,
                        latency=(time.perf_counter() - start_at),
                    ))
        except Exception as e:
            logging.exception("llm节点发生错误")
            self.agent_queue_manager.publish_error(state["task_id"], "llm节点发生错误")
            raise e

        if generation_type == "thought":
            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=id,
                task_id=state["task_id"],
                event=QueueEvent.AGENT_THOUGHT,
                thought=json.dumps(gathered.tool_calls),
                message=messages_to_dict(state["messages"]),
                latency=(time.perf_counter() - start_at),
            ))
        elif generation_type == "message":
            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=uuid.uuid4(),
                task_id=state["task_id"],
                event=QueueEvent.AGENT_END,
            ))

        return {"messages": [gathered], "iteration_count": state["iteration_count"] + 1}

    def _tools_node(self, state: AgentState) -> AgentState:
        """工具执行节点"""
        tools_by_name = {tool.name: tool for tool in self.agent_config.tools}

        tool_calls = state["messages"][-1].tool_calls

        messages = []
        for tool_call in tool_calls:
            id = uuid.uuid4()
            start_at = time.perf_counter()

            try:
                tool = tools_by_name[tool_call["name"]]
                tool_result = tool.invoke(tool_call["args"])
            except Exception as e:
                tool_result = f"工具执行错误: {str(e)}"

            messages.append(ToolMessage(
                tool_call_id=tool_call["id"],
                content=json.dumps(tool_result),
                name=tool_call["name"],
            ))

            event = QueueEvent.AGENT_ACTION if tool_call["name"] != DATASET_RETRIEVAL_TOOL_NAME else QueueEvent.DATASET_RETRIEVAL

            self.agent_queue_manager.publish(state["task_id"], AgentThought(
                id=id,
                task_id=state["task_id"],
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

    @classmethod
    def _preset_operation_condition(cls, state: AgentState) -> Literal["long_term_memory_recall", "__end__"]:
        """预设操作条件边, 用于判断是否触发预设响应"""
        message = state["messages"][-1]

        if message.type == "ai":
            return END

        return "long_term_memory_recall"
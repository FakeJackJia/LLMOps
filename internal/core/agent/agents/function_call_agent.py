from typing import Literal
from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.graph import StateGraph, END
from .base_agent import BaseAgent
from internal.core.agent.entities.agent_entity import AgentState

class FunctionCallAgent(BaseAgent):
    """基于函数/工具调用的智能体"""

    def run(self, query: str, history: list[AnyMessage] = None, long_term_memory: str = ""):
        """运行智能体应用, 并使用yield关键字返回对应的数据"""
        if history is None:
            history = []

        agent = self.build_graph()

        return agent.invoke({
            "messages": [HumanMessage(content=query)],
            "history": history,
            "long_term_memory": long_term_memory,
        })

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

    def _llm_node(self, state: AgentState) -> AgentState:
        """大语言模型节点"""

    def _tools_node(self, state: AgentState) -> AgentState:
        """工具执行节点"""

    @classmethod
    def _tools_condition(cls, state: AgentState) -> Literal["tools", "__end__"]:
        """检测下一步是执行tools还是结束"""
        message = state["messages"][-1]

        if hasattr(message, "tool_calls") and len(message.tool_calls) > 0:
            return "tools"

        return END
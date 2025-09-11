import re
from collections import defaultdict, deque
from typing import Any, TypedDict, Annotated
from uuid import UUID

from langchain_core.pydantic_v1 import BaseModel, Field, root_validator

from internal.exception import ValidateErrorException

from .edge_entity import BaseEdgeData
from .node_entity import NodeResult, BaseNodeData, NodeType
from .variable_entity import VariableValueType

# 工作流配置校验信息
WORKFLOW_CONFIG_NAME_PATTERN = r'^[A-Za-z][A-Za-z0-9_]*$'
WORKFLOW_CONFIG_DESCRIPTION_MAX_LENGTH = 1024

def _process_dict(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """工作流状态字典归纳函数"""
    left = left or {}
    right = right or {}

    return {**left, **right}

def _process_node_results(left: list[NodeResult], right: list[NodeResult]) -> list[NodeResult]:
    """工作流状态节点结果列表归纳函数"""
    left = left or []
    right = right or []

    return left + right

class WorkflowConfig(BaseModel):
    """工作流配置信息"""
    account_id: UUID # 用户账号id
    name: str = "" # 工作流名称, 必须是英文
    description: str = "" # 工作流描述用于告诉LLM什么时候调用workflow
    nodes: list[BaseNodeData] = Field(default_factory=list) # 工作流对应的节点
    edges: list[BaseEdgeData] = Field(default_factory=list) # 工作流对应的边

    @root_validator(pre=True)
    def validate_workflow_config(cls, values: dict[str, Any]):
        """校验工作流的所有参数配置"""
        name = values.get("name", None)
        if not name or not re.match(WORKFLOW_CONFIG_NAME_PATTERN, name):
            raise ValidateErrorException("工作流名字仅支持字母、数字和下划线, 且以字母开头")

        description = values.get("description", None)
        if not description or len(description) > WORKFLOW_CONFIG_DESCRIPTION_MAX_LENGTH:
            raise ValidateErrorException("工作流描述长度不能超过1024字符")

        nodes = values.get("nodes", [])
        edges = values.get("edges", [])

        if not isinstance(nodes, list) or len(nodes) ==0 :
            raise ValidateErrorException("工作流节点列表信息错误")
        if not isinstance(edges, list) or len(edges) ==0 :
            raise ValidateErrorException("工作流边列表信息错误")

        from internal.core.workflow.nodes import (
            CodeNodeData,
            DatasetRetrievalNodeData,
            EndNodeData,
            HttpRequestNodeData,
            LLMNodeData,
            StartNodeData,
            ToolNodeData,
            TemplateTransformNodeData,
        )

        node_data_classes = {
            NodeType.START: StartNodeData,
            NodeType.END: EndNodeData,
            NodeType.LLM: LLMNodeData,
            NodeType.TEMPLATE_TRANSFORM: TemplateTransformNodeData,
            NodeType.DATASET_RETRIEVAL: DatasetRetrievalNodeData,
            NodeType.CODE: CodeNodeData,
            NodeType.TOOL: ToolNodeData,
            NodeType.HTTP_REQUEST: HttpRequestNodeData,
        }

        node_data_dict = {}
        start_nodes = 0
        end_nodes = 0
        for node in nodes:
            if not isinstance(node, dict):
                raise ValidateErrorException("工作流节点数据类型出错")

            node_type = node.get("node_type", "")
            node_data_cls = node_data_classes.get(node_type, None)
            if not node_data_cls:
                raise ValidateErrorException("工作流节点类型出错")

            node_data = node_data_cls(**node)

            # 判断开始和结束节点是否唯一
            if node_data.node_type == NodeType.START:
                if start_nodes >= 1:
                    raise ValidateErrorException("工作流中只允许有一个开始节点")
                start_nodes += 1
            elif node_data.node_type == NodeType.END:
                if end_nodes >= 1:
                    raise ValidateErrorException("工作流中只允许有一个结束节点")
                end_nodes += 1

            # 判断nodes节点数据id是否唯一
            if node_data.id in node_data_dict:
                raise ValidateErrorException("工作流节点id必须唯一")

            # 判断nodes节点数据title是否唯一
            if any(item.title.strip() == node_data.title.strip() for item in node_data_dict.values()):
                raise ValidateErrorException("工作流节点title必须唯一")

            node_data_dict[node_data.id] = node_data

        edge_data_dict = {}
        for edge in edges:
            if not isinstance(edge, dict):
                raise ValidateErrorException("工作流边数据类型出错")

            edge_data = BaseEdgeData(**edge)

            # 判断edge id是否唯一
            if edge_data.id in edge_data_dict:
                raise ValidateErrorException("工作流边数据必须唯一")

            # 校验边中的source/target/source_type/target_type必须和nodes对应上
            if (
                edge_data.source not in node_data_dict
                or edge_data.source_type != node_data_dict[edge_data.source].node_type
                or edge_data.target not in node_data_dict
                or edge_data.target_type != node_data_dict[edge_data.target].node_type
            ):
                raise ValidateErrorException("工作流边找不到对应的边或边类型错误")

            # 校验edges里的边必须唯一(source + target必须唯一)
            if any(
                (item.source == edge_data.source and item.target == edge_data.target)
                for item in edge_data_dict.values()
            ):
                raise ValidateErrorException("工作流边数据不能重复添加")

            edge_data_dict[edge_data.id] = edge_data

        adj_list = cls._build_adj_list(edge_data_dict.values())
        reverse_adj_list = cls._build_reverse_adj_list(edge_data_dict.values())
        in_degree, out_degree = cls._build_degrees(edge_data_dict.values())

        #
        start_nodes = [node_data for node_data in node_data_dict.values() if in_degree[node_data.id] == 0]
        end_nodes = [node_data for node_data in node_data_dict.values() if out_degree[node_data.id] == 0]
        if (
            len(start_nodes) != 1
            or len(end_nodes) != 1
            or start_nodes[0].node_type != NodeType.START
            or end_nodes[0].node_type != NodeType.END
        ):
            raise ValidateErrorException("工作流里只允许开始节点入度为0且结束节点出度为0")

        start_node_data = start_nodes[0]
        if not cls._is_connected(adj_list, start_node_data.id):
            raise ValidateErrorException("工作流中存在不能到达的节点")

        if cls._has_cycle(start_node_data.id, adj_list):
            raise ValidateErrorException("工作流中不能存在环")

        # 校验数据引用是否正确
        cls._validate_inputs_ref(node_data_dict, reverse_adj_list)

        values["nodes"] = list(node_data_dict.values())
        values["edges"] = list(edge_data_dict.values())

        return values

    @classmethod
    def _validate_inputs_ref(
            cls,
            node_data_dict: dict[UUID, BaseNodeData],
            reverse_adj_list: defaultdict[Any, list]
    ) -> None:
        """校验输入数据引用"""
        for node_data in node_data_dict.values():
            predecessors = cls._get_predecessors(reverse_adj_list, node_data.id)

            if node_data.node_type != NodeType.START:
                variables = (
                    node_data.inputs if node_data.node_type != NodeType.END
                    else node_data.outputs
                )

                for variable in variables:
                    if variable.value.type == VariableValueType.REF:
                        if (
                            len(predecessors) == 0
                            or variable.value.content.ref_node_id not in predecessors
                        ):
                            raise ValidateErrorException("工作流数据引用错误")

                        ref_node_data = node_data_dict.get(variable.value.content.ref_node_id)

                        ref_variables = (
                            ref_node_data.inputs if ref_node_data.node_type == NodeType.START
                            else ref_node_data.outputs
                        )

                        if not any([ref_variable.name == variable.value.content.ref_var_name] for ref_variable in ref_variables):
                            raise ValidateErrorException(f"工作流节点{node_data.title}引用了不存在的节点变量")

    @classmethod
    def _is_connected(cls, adj_list: defaultdict[Any, list], start_node_id: UUID) -> bool:
        """检查是否流通"""
        visited = set()

        queue = deque([start_node_id])
        visited.add(start_node_id)

        while queue:
            node_id = queue.popleft()

            for neighbor in adj_list[node_id]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)

        return len(visited) == len(adj_list)

    @classmethod
    def _has_cycle(cls, start_node_id: UUID, adj_list: defaultdict[Any, list]) -> bool:
        """检查是否图中有环"""
        visited = set()
        rec_stack = set()

        def dfs(node_id: UUID) -> bool:
            """深度遍历"""
            visited.add(node_id)
            rec_stack.add(node_id)

            for neighbor in adj_list[node_id]:
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True

            rec_stack.remove(node_id)
            return False

        return dfs(start_node_id)

    @classmethod
    def _build_adj_list(cls, edges: list[BaseEdgeData]) -> defaultdict[Any, list]:
        """构建邻接表"""
        adj_list = defaultdict(list)

        for edge in edges:
            adj_list[edge.source].append(edge.target)

        return adj_list

    @classmethod
    def _build_reverse_adj_list(cls, edges: list[BaseEdgeData]) -> defaultdict[Any, list]:
        """构建逆邻接表"""
        reverse_adj_list = defaultdict(list)

        for edge in edges:
            reverse_adj_list[edge.target].append(edge.source)

        return reverse_adj_list

    @classmethod
    def _build_degrees(cls, edges: list[BaseEdgeData]) -> tuple[defaultdict[Any, int], defaultdict[Any, int]]:
        """in_degree和out_degree的计算"""
        in_degree = defaultdict(int)
        out_degree = defaultdict(int)

        for edge in edges:
            in_degree[edge.target] += 1
            out_degree[edge.source] += 1

        return in_degree, out_degree
    @classmethod
    def _get_predecessors(cls, reverse_adj_list: defaultdict[Any, list], target_node_id: UUID) -> list[UUID]:
        """根据传递的逆邻接表获取该目标节点的所有前置节点"""
        visited = set()
        predecessors = []

        def dfs(node_id: UUID):
            """深度遍历"""
            if node_id in visited:
                return

            visited.add(node_id)
            predecessors.append(node_id)

            for predecessor in reverse_adj_list[node_id]:
                dfs(predecessor)

        dfs(target_node_id)
        return predecessors

class WorkflowState(TypedDict):
    """工作流图程序状态字典"""
    inputs: Annotated[dict[str, Any], _process_dict] # 工作流的最初始输
    outputs: Annotated[dict[str, Any], _process_dict] # 工作流的最终输出结果
    node_results: Annotated[list[NodeResult], _process_node_results] # 各节点的运行结果
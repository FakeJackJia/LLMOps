import ast
from typing import Optional

from langchain_core.runnables import RunnableConfig

from internal.core.workflow.entities.workflow_entity import WorkflowState
from internal.core.workflow.nodes import BaseNode
from internal.core.workflow.entities.node_entity import NodeResult, NodeStatus
from internal.core.workflow.entities.variable_entity import VARIABLE_TYPE_DEFAULT_VALUE_MAP
from internal.exception import FailException
from internal.core.workflow.utils.helper import extract_variables_from_state

from .code_entity import CodeNodeData

class CodeNode(BaseNode):
    """Python代码运行节点"""
    _node_data_cls = CodeNodeData

    def invoke(self, state: WorkflowState, config: Optional[RunnableConfig] = None) -> WorkflowState:
        """python执行的代码函数名字必须为main, 并且参数名为params"""
        inputs_dict = extract_variables_from_state(self.node_data.inputs, state)

        # todo: 执行Python代码, 该方法目前有风险, 需迁移至沙箱里
        result = self._execute_function(self.node_data.code, params=inputs_dict)

        if not isinstance(result, dict):
            raise FailException("main返回值必须是字典")

        outputs_dict = {}
        outputs = self.node_data.outputs
        for output in outputs:
            # (非严格校验)
            outputs_dict[output.name] = result.get(
                output.name,
                VARIABLE_TYPE_DEFAULT_VALUE_MAP.get(output.type)
            )

        return {
            "node_results": [
                NodeResult(
                    node_data=self.node_data,
                    status=NodeStatus.SUCCEEDED,
                    inputs=inputs_dict,
                    outputs=outputs_dict
                )
            ]
        }

    @classmethod
    def _execute_function(cls, code: str, *args, **kwargs):
        """执行python函数代码"""
        try:
            # 解析代码为AST(抽象语法树)
            tree = ast.parse(code)

            # 定义变量用于检查是否找到main函数
            main_func = None

            for node in tree.body:
                if isinstance(node, ast.FunctionDef):
                    if node.name == "main":
                        if main_func:
                            raise FailException("代码中只能有一个main函数")

                        if len(node.args.args) != 1 or node.args.args[0].arg != "params":
                            raise FailException("main函数只能有param一个参数")

                        main_func = node
                    else:
                        raise FailException("代码中只能有main函数")
                else:
                    raise FailException("代码中只能包含函数定义, 不允许其他语句存在")

            if not main_func:
                raise FailException("未找到main函数")

            local_vars = {}
            exec(code, {}, local_vars)

            if "main" in local_vars and callable(local_vars["main"]):
                return local_vars["main"](*args, **kwargs)

            return FailException("main不可调用")
        except Exception as e:
            raise FailException("Python代码执行出错")
from dataclasses import dataclass
from typing import Any
from uuid import UUID
from injector import inject
from sqlalchemy import desc
from flask import request

from internal.schema.workflow_schema import CreateWorkflowReq, GetWorkflowsWithPageReq
from internal.model import Account, Workflow, ApiTool, Dataset
from internal.exception import ValidateErrorException, NotFoundException, ForbiddenException
from internal.entity.workflow_entity import DEFAULT_WORKFLOW_CONFIG, WorkflowStatus
from internal.core.workflow.entities.node_entity import NodeType
from internal.core.tools.builtin_tools.providers import BuiltinProviderManager

from .base_service import BaseService

from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class WorkflowService(BaseService):
    """工作流服务"""
    db: SQLAlchemy
    builtin_provider_manager: BuiltinProviderManager

    def create_workflow(self, req: CreateWorkflowReq, account: Account) -> Workflow:
        """创建工作流"""
        check_workflow = self.db.session.query(Workflow).filter(
            Workflow.tool_call_name == req.tool_call_name.data.strip(),
            Workflow.account_id == account.id,
        ).one_or_none()
        if check_workflow:
            raise ValidateErrorException("该工作流已被创建")

        return self.create(Workflow, **{
            **req.data,
            **DEFAULT_WORKFLOW_CONFIG,
            "account_id": account.id,
            "is_debug_passed": False,
            "status": WorkflowStatus.DRAFT,
            "tool_call_name": req.tool_call_name.name.strip()
        })

    def get_workflow(self, workflow_id: UUID, account: Account) -> Workflow:
        """获取工作流"""
        workflow = self.get(Workflow, workflow_id)

        if not workflow:
            raise NotFoundException("该工作流不存在")

        if workflow.account_id != account.id:
            raise ForbiddenException("当前账号无权限访问该工作流")

        return workflow

    def delete_workflow(self, workflow_id: UUID, account: Account) -> Workflow:
        """删除工作流"""
        workflow = self.get_workflow(workflow_id, account)

        self.delete(workflow)
        return workflow

    def update_workflow(self, workflow_id: UUID, account: Account, **kwargs) -> Workflow:
        """更新工作流"""
        workflow = self.get_workflow(workflow_id, account)

        check_workflow = self.db.session.query(Workflow).filter(
            Workflow.tool_call_name == kwargs.get("tool_call_name", "").strip(),
            Workflow.account_id == account.id,
            Workflow.id != workflow.id
        ).one_or_none()
        if check_workflow:
            raise ValidateErrorException("该工作流名字已存在")

        self.update(workflow, **kwargs)
        return workflow

    def get_workflows_with_page(self, req: GetWorkflowsWithPageReq, account: Account) -> tuple[list[Workflow], Paginator]:
        """获取工作流分页列表数据"""
        paginator = Paginator(db=self.db, req=req)

        filters = [Workflow.account_id == account.id]
        if req.search_word.data:
            filters.append(Workflow.name.ilike(f"%{req.search_word.data}%"))
        if req.status.data:
            filters.append(Workflow.status == req.status.data)

        workflows = paginator.paginate(
            self.db.session.query(Workflow).filter(*filters).order_by(desc("created_at"))
        )
        return workflows, paginator

    def update_draft_graph(self, workflow_id: UUID, draft_graph: dict[str, Any], account: Account) -> Workflow:
        """更新指定工作流草稿"""
        workflow = self.get_workflow(workflow_id, account)

        self.update(workflow, **{
            "draft_graph": draft_graph,
            "is_debug_passed": False
        })

        return workflow

    def get_draft_graph(self, workflow_id: UUID, account: Account) -> dict[str, Any]:
        """获取指定工作流草稿配置"""
        workflow = self.get_workflow(workflow_id, account)

        draft_graph = workflow.draft_graph

        for node in draft_graph["nodes"]:
            if node.get("node_type") == NodeType.TOOL:
                if node.get("type") == "builtin_tool":
                    provider = self.builtin_provider_manager.get_provider(node.get("provider_id"))
                    if not provider:
                        continue

                    tool_entity = provider.get_tool_entity(node.get("tool_id"))
                    if not tool_entity:
                        continue

                    param_keys = set([param.name for param in tool_entity.params])
                    params = node.get("params")
                    if params and set(params.keys()) - param_keys:
                        continue

                    provider_entity = provider.provider_entity
                    node["meta"] = {
                        "type": "builtin_tool",
                        "provider": {
                            "id": provider_entity.name,
                            "name": provider_entity.name,
                            "label": provider_entity.label,
                            "icon": f"{request.scheme}://{request.host}/builtin-tools/{provider_entity.name}/icon",
                            "description": provider_entity.description,
                        },
                        "tool": {
                            "id": tool_entity.name,
                            "name": tool_entity.name,
                            "label": tool_entity.label,
                            "description": tool_entity.description,
                            "params": params if params else {},
                        }
                    }
                else:
                    tool_record = self.db.session.query(ApiTool).filter(
                        ApiTool.provider_id == node.get("provider_id"),
                        ApiTool.name == node.get("tool_id"),
                        ApiTool.account_id == account.id
                    ).one_or_none()
                    if not tool_record:
                        continue

                    provider = tool_record.provider
                    node["meta"] = {
                        "type": "api_tool",
                        "provider": {
                            "id": str(provider.id),
                            "name": provider.name,
                            "label": provider.name,
                            "icon": provider.icon,
                            "description": provider.description,
                        },
                        "tool": {
                            "id": str(tool_record.id),
                            "name": tool_record.name,
                            "label": tool_record.name,
                            "description": tool_record.description,
                            "params": {},
                        },
                    }
            elif node.get("node_type") == NodeType.DATASET_RETRIEVAL:
                datasets = self.db.session.query(Dataset).filter(
                    Dataset.id.in_(node.get("dataset_ids", [])),
                    Dataset.account_id == account.id,
                ).all()
                node["meta"] = {
                    "datasets": [{
                        "id": dataset.id,
                        "name": dataset.name,
                        "icon": dataset.icon,
                        "description": dataset.description,
                    } for dataset in datasets]
                }

        return draft_graph
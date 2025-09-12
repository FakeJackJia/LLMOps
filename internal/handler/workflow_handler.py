from uuid import UUID
from dataclasses import dataclass
from injector import inject

from flask import request
from flask_login import current_user, login_required

from internal.schema.workflow_schema import (
    CreateWorkflowReq,
    UpdateWorkflowReq,
    GetWorkflowResp,
    GetWorkflowsWithPageReq,
    GetWorkflowsWithPageResp
)

from internal.service import WorkflowService
from pkg.response import validate_error_json, success_message, success_json
from pkg.paginator import PageModel

@inject
@dataclass
class WorkflowHandler:
    """工作流处理器"""
    workflow_service: WorkflowService

    @login_required
    def create_workflow(self):
        """创建工作流"""
        req = CreateWorkflowReq()
        if not req.validate():
            return validate_error_json(req.errors)

        workflow = self.workflow_service.create_workflow(req, current_user)
        return success_json({"id": workflow.id})

    @login_required
    def delete_workflow(self, workflow_id: UUID):
        """删除指定工作流"""
        self.workflow_service.delete_workflow(workflow_id, current_user)
        return success_message("删除工作流成功")

    @login_required
    def update_workflow(self, workflow_id: UUID):
        """更新指定工作流"""
        req = UpdateWorkflowReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.workflow_service.update_workflow(workflow_id, current_user, **req.data)
        return success_message("更新工作流成功")

    @login_required
    def get_workflow(self, workflow_id: UUID):
        """获取指定工作流信息"""
        workflow = self.workflow_service.get_workflow(workflow_id, current_user)

        resp = GetWorkflowResp()
        return success_json(resp.dump(workflow))

    @login_required
    def get_workflows_with_page(self):
        """获取工作流分页列表数据"""
        req = GetWorkflowsWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        workflows, paginator = self.workflow_service.get_workflows_with_page(req, current_user)

        resp = GetWorkflowsWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(workflows), paginator=paginator))

    @login_required
    def update_draft_graph(self, workflow_id: UUID):
        """更新工作流草稿"""
        draft_graph_dict = request.get_json(force=True, silent=True) or {"nodes": [], "edges": []}

        self.workflow_service.update_draft_graph(workflow_id, draft_graph_dict, current_user)
        return success_message("更新工作流草稿配置成功")

    @login_required
    def get_draft_graph(self, workflow_id: UUID):
        """获取指定工作流草稿配置"""
        draft_graph = self.workflow_service.get_draft_graph(workflow_id, current_user)
        return success_json(draft_graph)
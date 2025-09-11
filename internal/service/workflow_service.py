from dataclasses import dataclass
from uuid import UUID
from injector import inject
from sqlalchemy import desc

from internal.schema.workflow_schema import CreateWorkflowReq, GetWorkflowsWithPageReq
from internal.model import Account, Workflow
from internal.exception import ValidateErrorException, NotFoundException, ForbiddenException
from internal.entity.workflow_entity import DEFAULT_WORKFLOW_CONFIG, WorkflowStatus

from .base_service import BaseService

from pkg.paginator import Paginator
from pkg.sqlalchemy import SQLAlchemy


@inject
@dataclass
class WorkflowService(BaseService):
    """工作流服务"""
    db: SQLAlchemy

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
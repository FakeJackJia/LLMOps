from flask import request
from flask_login import login_required, current_user
from pkg.response import success_json, validate_error_json, success_message, compact_generate_response
from pkg.paginator import PageModel
from internal.service import (
    AppService,
    RetrievalService,
)
from internal.schema.app_schema import (
    CreateAppReq,
    GetAppResp,
    GetPublishHistoriesWithPageReq,
    GetPublishHistoriesWithPageResp,
    FallbackHistoryToDraftReq,
    UpdateDebugConversationSummaryReq,
    DebugChatReq,
    GetDebugConversationMessagesWithPageReq,
    GetDebugConversationMessagesWithPageResp,
    UpdateAppReq,
    GetAppsWithPageReq,
    GetAppsWithPageResp,
)
from internal.core.language_model import LanguageModelManager

from dataclasses import dataclass
from injector import inject
from uuid import UUID

@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    retrieval_service: RetrievalService
    language_model_manager: LanguageModelManager

    @login_required
    def create_app(self):
        """调用服务创建新的APP记录"""
        req = CreateAppReq()
        if not req.validate():
            return validate_error_json(req.errors)

        app = self.app_service.create_app(req, current_user)
        return success_json({"id": app.id})

    @login_required
    def get_app(self, app_id: UUID):
        """获取指定的应用基础信息"""
        app = self.app_service.get_app(app_id, current_user)

        resp = GetAppResp()
        return success_json(resp.dump(app))

    @login_required
    def update_app(self, app_id: UUID):
        """根据传递的信息更新指定的应用"""
        req = UpdateAppReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.app_service.update_app(app_id, current_user, **req.data)
        return success_message("更新Agent应用成功")

    @login_required
    def delete_app(self, app_id: UUID):
        """根据传递的信息删除指定的应用"""
        self.app_service.delete_app(app_id, current_user)
        return success_message("删除Agent应用成功")

    @login_required
    def get_apps_with_page(self):
        """获取当前登录账号的应用分页列表数据"""
        req = GetAppsWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        apps, paginator = self.app_service.get_apps_with_page(req, current_user)

        resp = GetAppsWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(apps), paginator=paginator))

    @login_required
    def copy_app(self, app_id: UUID):
        """根据传递的应用id快速拷贝该应用"""
        app = self.app_service.copy_app(app_id, current_user)
        return success_json({"id": app.id})

    @login_required
    def get_draft_app_config(self, app_id: UUID):
        """根据传递的应用id获取应用的最新草稿配置"""
        draft_config = self.app_service.get_draft_app_config(app_id, current_user)
        return success_json(draft_config)

    @login_required
    def update_draft_app_config(self, app_id: UUID):
        """根据传递的应用id+草稿配置更新应用最新的草稿配置"""
        draft_app_config = request.get_json(force=True, silent=True) or {}

        self.app_service.update_draft_app_config(app_id, draft_app_config, current_user)
        return success_message("更新应用草稿配置成功")

    @login_required
    def publish(self, app_id: UUID):
        """发布传递的应用id/更新特定的草稿配置"""
        self.app_service.publish_draft_app_config(app_id, current_user)
        return success_message("发布/更新应用配置成功")

    @login_required
    def cancel_publish(self, app_id: UUID):
        """根据传递的应用id取消发布"""
        self.app_service.cancel_publish_app_config(app_id, current_user)
        return success_message("取消发布应用成功")

    @login_required
    def get_publish_histories_with_page(self, app_id: UUID):
        """根据传递的应用id, 获取应用发布历史列表"""
        req = GetPublishHistoriesWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        app_config_versions, paginator  = self.app_service.get_publish_histories_with_page(app_id, req, current_user)

        resp = GetPublishHistoriesWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(app_config_versions), paginator=paginator))

    @login_required
    def fallback_history_to_draft(self, app_id: UUID):
        """根据传递的应用id+历史版本配置id, 回退到草稿中"""
        req = FallbackHistoryToDraftReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.app_service.fallback_history_to_draft(app_id, req.app_config_version_id.data, current_user)
        return success_message("回退历史配置至草稿成功")

    @login_required
    def get_debug_conversation_summary(self, app_id: UUID):
        """根据传递的应用id获取调试会话长期记忆"""
        summary = self.app_service.get_debug_conversation_summary(app_id, current_user)
        return success_json({"summary": summary})

    @login_required
    def update_debug_conversation_summary(self, app_id: UUID):
        """根据传递的应用id+摘要信息更新调试会话长期记忆"""
        req = UpdateDebugConversationSummaryReq()
        if not req.validate():
            return validate_error_json(req.errors)

        self.app_service.update_debug_conversation_summary(app_id, req.summary.data, current_user)
        return success_message("更新AI应用长期记忆成功")

    @login_required
    def delete_debug_conversation(self, app_id: UUID):
        """根据传递的应用id, 清空该应用的调试会话记录"""
        self.app_service.delete_debug_conversation(app_id, current_user)
        return success_message("清空应用调试会话成功")

    @login_required
    def debug_chat(self, app_id: UUID):
        """根据传递的应用id+query, 发起调试对话"""
        req = DebugChatReq()
        if not req.validate():
            return validate_error_json(req.errors)

        response = self.app_service.debug_chat(app_id, req.query.data, current_user)
        return compact_generate_response(response)

    @login_required
    def stop_debug_chat(self, app_id: UUID, task_id: UUID):
        """根据传递的应用id+任务id停止某个应用的指定调试会话"""
        self.app_service.stop_debug_chat(app_id, task_id, current_user)
        return success_message("停止应用调试会话成功")

    @login_required
    def get_debug_conversation_messages_with_page(self, app_id: UUID):
        """根据传递的应用id, 获取该应用的调试会话分页列表记录"""
        req = GetDebugConversationMessagesWithPageReq(request.args)
        if not req.validate():
            return validate_error_json(req.errors)

        messages, paginator = self.app_service.get_debug_conversation_messages_with_page(
            app_id,
            req,
            current_user
        )

        resp = GetDebugConversationMessagesWithPageResp(many=True)
        return success_json(PageModel(list=resp.dump(messages), paginator=paginator))

    @login_required
    def ping(self):
        provider = self.language_model_manager.get_provider("tongyi")
        model_entity = provider.get_model_entity("qwen-max")
        model_cls = provider.get_model_class(model_entity.model_type)
        llm = model_cls(**{
            **model_entity.attributes,
            "features": model_entity.features,
            "metadata": model_entity.meta_data
        })
        return success_json({
            "content": llm.invoke("你好 你是").content,
            "features": llm.features,
            "metadata": llm.metadata
        })
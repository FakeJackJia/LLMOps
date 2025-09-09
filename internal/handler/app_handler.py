import uuid

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
from dataclasses import dataclass
from injector import inject
from uuid import UUID

@inject
@dataclass
class AppHandler:
    """应用控制器"""
    app_service: AppService
    retrieval_service: RetrievalService

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
        from internal.core.workflow import Workflow
        from internal.core.workflow.entities.workflow_entity import WorkflowConfig

        nodes = [
            {
                "id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                "node_type": "start",
                "title": "开始",
                "description": "工作流的起点节点，支持定义工作流的起点输入等信息。",
                "inputs": [
                    {
                        "name": "query",
                        "type": "string",
                        "description": "用户输入的query信息",
                        "required": True,
                        "value": {
                            "type": "generated",
                            "content": "",
                        }
                    },
                    {
                        "name": "location",
                        "type": "string",
                        "description": "需要查询的城市地址信息",
                        "required": False,
                        "value": {
                            "type": "generated",
                            "content": "",
                        }
                    },
                ]
            },
            {
                "id": "eba75e0b-21b7-46ed-8d21-791724f0740f",
                "node_type": "llm",
                "title": "大语言模型",
                "description": "",
                "inputs": [
                    {
                        "name": "query",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                                "ref_var_name": "query",
                            },
                        }
                    },
                ],
                "prompt": (
                    "你是一个强有力的AI机器人，请根据用户的提问回复特定的内容，用户的提问是: {{query}}"
                ),
                "model_config": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "parameters": {
                        "temperature": 0.5,
                        "top_p": 0.85,
                        "frequency_penalty": 0.2,
                        "presence_penalty": 0.2,
                        "max_tokens": 8192,
                    },
                }
            },
            {
                "id": "623b7671-0bc2-446c-bf5e-5e25032a522e",
                "node_type": "template_transform",
                "title": "模板转换",
                "description": "",
                "inputs": [
                    {
                        "name": "location",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                                "ref_var_name": "location",
                            },
                        }
                    },
                    {
                        "name": "query",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                                "ref_var_name": "query"
                            }
                        }
                    }
                ],
                "template": "地址: {{location}}\n提问内容: {{query}}",
            },
            {
                "id": "860c8411-37ed-4872-b53f-30afa0290211",
                "node_type": "end",
                "title": "结束",
                "description": "工作流的结束节点，支持定义工作流最终输出的变量等信息。",
                "outputs": [
                    {
                        "name": "query",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                                "ref_var_name": "query",
                            },
                        }
                    },
                    {
                        "name": "location",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
                                "ref_var_name": "location",
                            },
                        }
                    },
                    {
                        "name": "username",
                        "type": "string",
                        "value": {
                            "type": "literal",
                            "content": "jack"
                        }
                    },
                    {
                        "name": "template_combine",
                        "type": "string",
                        "value": {
                            "type": "ref",
                            "content": {
                                "ref_node_id": "623b7671-0bc2-446c-bf5e-5e25032a522e",
                                "ref_var_name": "output"
                            }
                        }
                    }
                ]
            }
        ]
        edges = [{
            "id": "51e993f4-a832-48bc-8211-59b37acf688c",
            "source": "18d938c4-ecd7-4a6b-9403-3625224b96cc",
            "source_type": "start",
            "target": "eba75e0b-21b7-46ed-8d21-791724f0740f",
            "target_type": "llm"
        },
        {
            "id": "51e993f4-a832-48bc-8211-59b37acf688c",
            "source": "eba75e0b-21b7-46ed-8d21-791724f0740f",
            "source_type": "llm",
            "target": "623b7671-0bc2-446c-bf5e-5e25032a522e",
            "target_type": "template_transform"
        },
        {
            "id": "675fcd37-f308-8008-a6f4-389a0b1ed0ca",
            "source": "623b7671-0bc2-446c-bf5e-5e25032a522e",
            "source_type": "template_transform",
            "target": "860c8411-37ed-4872-b53f-30afa0290211",
            "target_type": "end"
        }
        ]

        workflow = Workflow(workflow_config=WorkflowConfig(
            name="workflow",
            description="工作流组件",
            nodes=nodes,
            edges=edges
        ))

        res = workflow.invoke({"query": "你好", "location": "苏州"})

        return success_json({
            **res,
            "info": {
                "name": workflow.name,
                "description": workflow.description,
                "args_schema": workflow.args_schema.schema()
            },
            "node_results": [node_result.dict() for node_result in res['node_results']]
        })
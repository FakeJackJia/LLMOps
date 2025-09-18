import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from injector import inject
from dataclasses import dataclass

from internal.model import Account, App, Message
from .base_service import BaseService
from .app_service import AppService

from pkg.sqlalchemy import SQLAlchemy
from redis import Redis

@inject
@dataclass
class AnalysisService(BaseService):
    """统计分析服务"""
    db: SQLAlchemy
    redis_client: Redis
    app_service: AppService

    def get_app_analysis(self, app_id: UUID, account: Account) -> dict[str, Any]:
        """根据应用id和账号获取应用分析信息"""
        app = self.app_service.get_app(app_id, account)

        today = datetime.now()
        today_midnight = datetime.combine(today, datetime.min.time())
        seven_days_ago = today_midnight - timedelta(days=7)
        fourteen_days_ago = today_midnight - timedelta(days=14)

        cache_key = f"{today.strftime('%Y_%m_%d')}:{str(app.id)}"

        try:
            if self.redis_client.exists(cache_key):
                app_analysis = self.redis_client.get(cache_key)
                return json.loads(app_analysis)
        except Exception:
            pass

        seven_days_messages = self.get_messages_by_time_range(app, seven_days_ago, today_midnight)
        fourteen_days_messages = self.get_messages_by_time_range(app, fourteen_days_ago, seven_days_ago)

        # 计算数据: 全部会话数、激活用户数、平均会话互动数、token输出速度、费用消耗
        seven_overview = self.calculate_overview_indicators_by_messages(seven_days_messages)
        fourteen_overview = self.calculate_overview_indicators_by_messages(fourteen_days_messages)

        # 统计环比数据
        pop = self.calculate_pop_by_overview_indicators(seven_overview, fourteen_overview)

        # 趋势计算
        trend = self.calculate_trend_by_messages(today_midnight, 7, seven_days_messages)

        fields = [
            "total_messages", "active_accounts", "avg_of_conversation_messages",
            "token_output_rate", "cost_consumption"
        ]

        app_analysis = {
            **trend,
            **{
                field: {
                    "data": seven_overview.get(field),
                    "pop": pop.get(field)
                } for field in fields
            }
        }

        self.redis_client.setex(cache_key, 24 * 60 * 60, json.dumps(app_analysis))
        return app_analysis


    def get_messages_by_time_range(self, app: App, start_at: datetime, end_at: datetime) -> list[Message]:
        """根据时间段获取指定消息会话"""
        return self.db.session.query(Message).with_entities(
            Message.id, Message.conversation_id, Message.created_by,
            Message.latency, Message.total_token_count, Message.total_price,
            Message.created_at
        ).filter(
            Message.app_id == app.id,
            Message.created_at >= start_at,
            Message.created_at < end_at,
            Message.answer != "",
        ).all()

    @classmethod
    def calculate_overview_indicators_by_messages(cls, messages: list[Message]) -> dict[str, Any]:
        """根据消息列表计算数据"""
        # 全部会话数
        total_messages = len(messages)

        # 激活用户数
        active_accounts = len({message.created_by for message in messages})

        # 平均会话互动数
        avg_of_conversation_messages = 0
        conversation_count = len({message.conversation_id for message in messages})
        if conversation_count != 0:
            avg_of_conversation_messages = total_messages / conversation_count

        # token输出速度
        token_output_rate = 0
        latency_sum = sum(message.latency for message in messages)
        if latency_sum != 0:
            token_output_rate = sum(message.total_token_count for message in messages) / latency_sum

        # 费用消耗
        cost_consumption = sum(message.total_price for message in messages)

        return {
            "total_messages": total_messages,
            "active_accounts": active_accounts,
            "avg_of_conversation_messages": float(avg_of_conversation_messages),
            "token_output_rate": float(token_output_rate),
            "cost_consumption": float(cost_consumption)
        }

    @classmethod
    def calculate_pop_by_overview_indicators(
            cls,
            current_data: dict[str, Any],
            previous_data: dict[str, Any]
    ) -> dict[str, Any]:
        """计算环比数据"""
        pop = {}

        fields = [
            "total_messages", "active_accounts", "avg_of_conversation_messages",
            "token_output_rate", "cost_consumption"
        ]

        for field in fields:
            current_val = current_data.get(field)
            previous_val = previous_data.get(field)

            if previous_val != 0:
                pop[field] = float((current_val - previous_val) / previous_val)
            else:
                pop[field] = 0

        return pop

    @classmethod
    def calculate_trend_by_messages(
            cls,
            end_at: datetime,
            days_ago: int,
            messages: list[Message]
    ) -> dict[str, Any]:
        """根据结束时间、回退天数、消息列表计算对应的指标趋势数据"""
        end_at = datetime.combine(end_at, datetime.min.time())

        total_messages_trend = {"x_axis": [], "y_axis": []}
        active_accounts_trend = {"x_axis": [], "y_axis": []}
        avg_of_conversation_messages_trend = {"x_axis": [], "y_axis": []}
        cost_consumption_trend = {"x_axis": [], "y_axis": []}

        for day in range(days_ago):
            trend_start_at = end_at - timedelta(days_ago - day)
            trend_end_at = end_at - timedelta(days_ago - day - 1)

            total_messages_trend_y_axis = len([
                message for message in messages
                if trend_start_at <= message.created_at < trend_end_at
            ])
            total_messages_trend["x_axis"].append(int(trend_start_at.timestamp()))
            total_messages_trend["y_axis"].append(total_messages_trend_y_axis)

            active_accounts_trend_y_axis = len({
                message.created_by for message in messages
                if trend_start_at <= message.created_at < trend_end_at
            })
            active_accounts_trend["x_axis"].append(int(trend_start_at.timestamp()))
            active_accounts_trend["y_axis"].append(active_accounts_trend_y_axis)

            avg_of_conversation_messages_trend_y_axis = 0
            conversation_count = len({
                message.conversation_id for message in messages
                if trend_start_at <= message.created_at < trend_end_at
            })
            if conversation_count != 0:
                avg_of_conversation_messages_trend_y_axis = total_messages_trend_y_axis / conversation_count
            avg_of_conversation_messages_trend["x_axis"].append(int(trend_start_at.timestamp()))
            avg_of_conversation_messages_trend["y_axis"].append(float(avg_of_conversation_messages_trend_y_axis))

            cost_consumption_trend_y_axis = float(sum(
                message.total_price for message in messages
                if trend_start_at <= message.created_at < trend_end_at
            ))
            cost_consumption_trend["x_axis"].append(int(trend_start_at.timestamp()))
            cost_consumption_trend["y_axis"].append(cost_consumption_trend_y_axis)

        return {
            "total_messages_trend": total_messages_trend,
            "active_accounts_trend": active_accounts_trend,
            "avg_of_conversation_messages_trend": avg_of_conversation_messages_trend,
            "cost_consumption_trend": cost_consumption_trend
        }
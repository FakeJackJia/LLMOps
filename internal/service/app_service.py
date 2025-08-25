
import uuid
from dataclasses import dataclass
from injector import inject
from pkg.sqlalchemy import SQLAlchemy
from internal.model import App

@inject
@dataclass
class AppService:
    """应用服务逻辑"""
    db: SQLAlchemy

    def create_app(self) -> App:
        with self.db.auto_commit():
            app = App(name="测试机器人", account_id=uuid.uuid4(), icon="", description="这是一个简单的聊天机器人")
            self.db.session.add(app)

        return app

    def get_app(self, id: uuid.UUID) -> App:
        app = self.db.session.query(App).get(id)

        return app

    def update_app(self, id: uuid.UUID) -> App:
        with self.db.auto_commit():
            app = self.get_app(id)
            app.name = "Imooc聊天机器人"

        return app

    def delete_app(self, id: uuid.UUID) -> App:
        with self.db.auto_commit():
            app = self.get_app(id)
            self.db.session.delete(app)

        return app
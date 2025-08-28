from injector import Injector
from injector import Binder, Module
from pkg.sqlalchemy import SQLAlchemy
from internal.extension.database_extension import db
from internal.extension.migrate_extension import migrate
from internal.extension.redis_extension import redis_client
from internal.extension.login_extension import login_manager
from flask_migrate import Migrate
from flask_login import LoginManager
from redis import Redis

class ExtensionModule(Module):
    """扩展模块的依赖注入"""
    def configure(self, binder: Binder) -> None:
        binder.bind(SQLAlchemy, to=db)
        binder.bind(Migrate, to=migrate)
        binder.bind(Redis, to=redis_client)
        binder.bind(LoginManager, to=login_manager)


injector = Injector([ExtensionModule])
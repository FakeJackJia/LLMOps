from injector import Binder, Module
from pkg.sqlalchemy import SQLAlchemy
from internal.extension.database_extension import db
from internal.extension.migrate_extension import migrate
from flask_migrate import Migrate

class ExtensionModule(Module):
    """扩展模块的依赖注入"""
    def configure(self, binder: Binder) -> None:
        binder.bind(SQLAlchemy, to=db)
        binder.bind(Migrate, to=migrate)
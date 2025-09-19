import os

# 猴子补丁
if os.environ.get("FLASK_DEBUG") == "0" or os.environ.get("FLASK_ENV") == "production":
    from gevent import monkey
    monkey.patch_all()

    import grpc.experimental.gevent
    grpc.experimental.gevent.init_gevent()

import dotenv
from .module import injector
from internal.server import Http
from internal.router import Router
from internal.middleware import Middleware
from config import Config
from pkg.sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

# 将env加载到环境变量中
dotenv.load_dotenv()
conf = Config()

app = Http(__name__,
           conf=conf,
           db=injector.get(SQLAlchemy),
           migrate=injector.get(Migrate),
           router=injector.get(Router),
           login_manager=injector.get(LoginManager),
           middleware=injector.get(Middleware))

celery = app.extensions["celery"]

if __name__ == '__main__':
    app.run(debug=True)
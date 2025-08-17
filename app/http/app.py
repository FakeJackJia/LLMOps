
import dotenv
from injector import Injector
from internal.server import Http
from internal.router import Router
from config import Config
from pkg.sqlalchemy import SQLAlchemy
from .module import ExtensionModule
from flask_migrate import Migrate

# 将env加载到环境变量中
dotenv.load_dotenv()
conf = Config()

injector = Injector([ExtensionModule])

app = Http(__name__,
           conf=conf,
           db=injector.get(SQLAlchemy),
           migrate=injector.get(Migrate),
           router=injector.get(Router))

celery = app.extensions["celery"]

if __name__ == '__main__':
    app.run(debug=True)
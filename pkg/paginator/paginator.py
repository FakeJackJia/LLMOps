import math
from typing import Any
from flask_wtf import FlaskForm
from wtforms import IntegerField
from wtforms.validators import Optional, NumberRange
from dataclasses import dataclass
from pkg.sqlalchemy import SQLAlchemy

class PaginatorReq(FlaskForm):
    """分页请求基础类, 涵盖当前页数、每页条数, 如果接口请求需要携带分页信息, 可直接继承该类"""
    current_page = IntegerField("current_page", default=1, validators=[
        Optional(),
        NumberRange(min=1, max=9999, message="当前页数的范围在1-9999")
    ])
    page_size = IntegerField("page_size", default=20, validators=[
        Optional(),
        NumberRange(min=1, max=50, message="每页数据的条数范围在1-50")
    ])

@dataclass
class Paginator:
    """分页器"""
    total_page: int = 0 # 总页数
    total_record: int = 0 # 总条数
    current_page: int = 1 # 当前页数
    page_size: int = 20 # 每条页数

    def __init__(self, db: SQLAlchemy, req: PaginatorReq = None):
        if req is not None:
            self.current_page = req.current_page.data
            self.page_size = req.page_size.data
        self.db = db

    def paginate(self, select) -> list[Any]:
        """对传入的查询进行分页"""
        p = self.db.paginate(select, page=self.current_page, per_page=self.page_size, error_out=False)

        # 计算总页数+总条数
        self.total_record = p.total
        self.total_page = math.ceil(p.total / self.page_size)

        return p.items

@dataclass
class PageModel:
    list: list[Any]
    paginator: Paginator
import os
from typing import Any
from injector import inject
from dataclasses import dataclass
import jwt
from internal.exception import UnauthorizedException

@inject
@dataclass
class JwtService:
    """
    jwt服务: jwt包含Header(元数据信息, 例如算法), Payload(主体信息, 例如用户id), Signature(验证JWT完整性)
    Signature通过对header和payload进行哈希运算并用私钥加密生成
    """

    @classmethod
    def generate_token(cls, payload: dict[str, Any]) -> str:
        """根据传递的载荷信息生成token信息"""
        secret_key = os.getenv("JWT_SECRET_KEY")
        return jwt.encode(payload, secret_key, algorithm="HS256")

    @classmethod
    def parse_token(cls, token: str) -> dict[str, Any]:
        """解析传入的token信息得到载荷"""
        secret_key = os.getenv("JWT_SECRET_KEY")
        try:
            return jwt.decode(token, secret_key, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise UnauthorizedException("授权认证凭证已过期请重新登入")
        except jwt.InvalidTokenError:
            raise UnauthorizedException("解析token出错, 请重新登录")
        except Exception as e:
            raise UnauthorizedException(str(e))
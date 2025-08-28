from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class OAuthUserInfo:
    """OAuth用户基础信息, 只记录id/name/email"""
    id: str
    name: str
    email: str

@dataclass
class OAuth(ABC):
    """第三方OAuth授权认证基础类"""
    client_id: str
    client_secret: str
    redirect_uri: str

    @abstractmethod
    def get_provider(self) -> str:
        """获取服务提供者对应的名字"""

    @abstractmethod
    def get_authorization_url(self) -> str:
        """获取跳转授权认证的URL地址"""

    @abstractmethod
    def get_access_token(self, code: str) -> str:
        """根据传入的code代码获取授权令牌"""

    @abstractmethod
    def get_raw_user_info(self, token: str) -> dict:
        """根据传入的token获取OAuth原始信息"""

    def get_user_info(self, token: str) -> OAuthUserInfo:
        """根据传入的token获取OAuthUserInfo信息"""
        raw_info = self.get_raw_user_info(token)
        return self._transform_user_info(raw_info)

    @abstractmethod
    def _transform_user_info(self, raw_info: dict) -> OAuthUserInfo:
        """将OAuth原始信息转成OAuthUserInfo"""
"""自定义异常模块"""

from typing import Optional, Any
from utils.response_code import ResponseCode


class BaseAPIException(Exception):
    """API基础异常类"""

    def __init__(
        self,
        response_code: ResponseCode,
        detail: Optional[str] = None,
        data: Optional[Any] = None,
    ):
        self.response_code = response_code
        self.detail = detail or response_code.message
        self.data = data
        super().__init__(self.detail)


class AuthenticationException(BaseAPIException):
    """认证异常"""

    def __init__(self, detail: Optional[str] = None, data: Optional[Any] = None):
        super().__init__(ResponseCode.UNAUTHORIZED, detail, data)

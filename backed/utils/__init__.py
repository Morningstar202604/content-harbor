"""通用工具包

约定：本包内模块应可脱离本项目业务模型独立复用。
业务权限（SsoUser 等）请使用 core.permissions。
"""

from utils.auth import JWTAuthenticator, create_jwt_authenticator_from_settings, jwt_authenticator
from utils.custom_exceptions import (
    AuthenticationException,
    BaseAPIException,
)
from utils.logger import (
    get_logger,
    get_security_logger,
    log_api_access,
    log_security_event,
    setup_logger,
    setup_logging,
)
from utils.masking import mask_email, mask_middle, mask_phone, mask_id_card
from utils.response_code import ResponseCode
from utils.security import SecurityUtil

# Re-exports for backward compatibility
__all__ = [
    'JWTAuthenticator', 'create_jwt_authenticator_from_settings', 'jwt_authenticator',
    'AuthenticationException', 'BaseAPIException',
    'get_logger', 'get_security_logger', 'log_api_access', 'log_security_event',
    'setup_logger', 'setup_logging',
    'mask_email', 'mask_middle', 'mask_phone', 'mask_id_card',
    'ResponseCode', 'SecurityUtil',
]

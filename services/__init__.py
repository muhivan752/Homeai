# ===============================
# services/__init__.py - Service Exports
# ===============================
# Export all service classes for type hints and direct imports.
# 
# NOTE: init_services() is in container.py to avoid duplication.
# Use: from services.container import init_services

from services.base import BaseService
from services.user import UserService
from services.device import DeviceService
from services.energy import EnergyService
from services.admin import AdminService
from services.container import init_services, get_service_info

__all__ = [
    # Base
    'BaseService',
    
    # Services
    'UserService',
    'DeviceService',
    'EnergyService',
    'AdminService',
    
    # Container
    'init_services',
    'get_service_info',
]

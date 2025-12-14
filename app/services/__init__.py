"""
Services package initialization
Safe import handling for all services
"""
import logging

logger = logging.getLogger(__name__)

# Safe imports for all services
def safe_import(module_name, service_name):
    """Safely import a service module"""
    try:
        module = __import__(f'services.{module_name}', fromlist=[service_name])
        return getattr(module, service_name)
    except ImportError as e:
        logger.warning(f"Could not import {service_name} from {module_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Error importing {service_name}: {e}")
        return None

# Initialize all services safely
analytics_service = safe_import('analytics_service', 'analytics_service')
smart_ai_service = safe_import('smart_ai_service', 'smart_ai_service')
smart_notification_service = safe_import('smart_notifications', 'smart_notification_service')
security_service = safe_import('security_service', 'security_service')
ui_service = safe_import('ui_service', 'ui_service')
automation_service = safe_import('automation_service', 'automation_service')
multi_tenant_service = safe_import('multi_tenant_service', 'multi_tenant_service')
gamification_service = safe_import('gamification_service', 'gamification_service')
integration_service = safe_import('integration_service', 'integration_service')

# Log which services are available
available_services = []
for service_name, service in [
    ('analytics_service', analytics_service),
    ('smart_ai_service', smart_ai_service),
    ('smart_notification_service', smart_notification_service),
    ('security_service', security_service),
    ('ui_service', ui_service),
    ('automation_service', automation_service),
    ('multi_tenant_service', multi_tenant_service),
    ('gamification_service', gamification_service),
    ('integration_service', integration_service)
]:
    if service is not None:
        available_services.append(service_name)

logger.info(f"Available services: {', '.join(available_services)}")

# Export all services
__all__ = [
    'analytics_service',
    'smart_ai_service', 
    'smart_notification_service',
    'security_service',
    'ui_service',
    'automation_service',
    'multi_tenant_service',
    'gamification_service',
    'integration_service'
]
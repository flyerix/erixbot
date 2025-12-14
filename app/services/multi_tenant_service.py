"""
Multi-Tenant System
Support for multiple organizations with data isolation
"""
import logging
from datetime import datetime, timezone
from collections import defaultdict
from sqlalchemy import and_, or_, desc, func
from models import SessionLocal, List, Ticket, UserActivity, AuditLog
import json
import os

logger = logging.getLogger(__name__)

class MultiTenantService:
    """Multi-tenant service for organization isolation"""
    
    def __init__(self):
        self.tenants = {}
        self.user_tenant_mapping = {}
        self.tenant_configs = {}
        self.load_tenant_configurations()
    
    def load_tenant_configurations(self):
        """Load tenant configurations from environment or config file"""
        try:
            # Default tenant (main organization)
            self.tenants['default'] = {
                'name': 'ErixCast Main',
                'admin_ids': self._parse_admin_ids(os.getenv('ADMIN_IDS', '')),
                'features': {
                    'ai_assistance': True,
                    'auto_renewals': True,
                    'analytics': True,
                    'notifications': True
                },
                'limits': {
                    'max_lists': 1000,
                    'max_tickets_per_user': 50,
                    'max_users': 10000
                },
                'branding': {
                    'bot_name': 'ErixCast Bot',
                    'primary_color': '#667eea',
                    'logo_url': None
                }
            }
            
            # Load additional tenants from environment
            tenant_configs = os.getenv('TENANT_CONFIGS', '{}')
            if tenant_configs:
                additional_tenants = json.loads(tenant_configs)
                self.tenants.update(additional_tenants)
            
            logger.info(f"Loaded {len(self.tenants)} tenant configurations")
            
        except Exception as e:
            logger.error(f"Error loading tenant configurations: {e}")
    
    def _parse_admin_ids(self, admin_ids_str):
        """Parse admin IDs from string"""
        if not admin_ids_str:
            return []
        
        try:
            return [int(admin_id.strip()) for admin_id in admin_ids_str.split(',') if admin_id.strip()]
        except ValueError as e:
            logger.error(f"Error parsing admin IDs: {e}")
            return []
    
    def get_user_tenant(self, user_id):
        """Get tenant for specific user"""
        return self.user_tenant_mapping.get(user_id, 'default')
    
    def assign_user_to_tenant(self, user_id, tenant_id, admin_id=None):
        """Assign user to specific tenant"""
        try:
            if tenant_id not in self.tenants:
                return False, f"Tenant {tenant_id} does not exist"
            
            old_tenant = self.user_tenant_mapping.get(user_id, 'default')
            self.user_tenant_mapping[user_id] = tenant_id
            
            # Log the assignment
            with SessionLocal() as session:
                audit_log = AuditLog(
                    admin_id=admin_id or 0,
                    action='assign_user_tenant',
                    target_type='user',
                    target_id=user_id,
                    old_value=old_tenant,
                    new_value=tenant_id,
                    details=json.dumps({
                        'user_id': user_id,
                        'old_tenant': old_tenant,
                        'new_tenant': tenant_id
                    }),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"User {user_id} assigned to tenant {tenant_id}")
            return True, "User assigned successfully"
            
        except Exception as e:
            logger.error(f"Error assigning user to tenant: {e}")
            return False, str(e)
    
    def get_tenant_config(self, tenant_id):
        """Get configuration for specific tenant"""
        return self.tenants.get(tenant_id, self.tenants['default'])
    
    def is_user_admin(self, user_id, tenant_id=None):
        """Check if user is admin for their tenant"""
        if tenant_id is None:
            tenant_id = self.get_user_tenant(user_id)
        
        tenant_config = self.get_tenant_config(tenant_id)
        return user_id in tenant_config.get('admin_ids', [])
    
    def get_tenant_lists(self, tenant_id, session=None):
        """Get lists for specific tenant"""
        try:
            if session is None:
                with SessionLocal() as session:
                    return self._get_tenant_lists_query(tenant_id, session)
            else:
                return self._get_tenant_lists_query(tenant_id, session)
                
        except Exception as e:
            logger.error(f"Error getting tenant lists: {e}")
            return []
    
    def _get_tenant_lists_query(self, tenant_id, session):
        """Internal method to get tenant lists"""
        # For now, all tenants share the same lists
        # In a full implementation, you'd add tenant_id to List model
        return session.query(List).all()
    
    def get_tenant_tickets(self, tenant_id, session=None):
        """Get tickets for specific tenant"""
        try:
            if session is None:
                with SessionLocal() as session:
                    return self._get_tenant_tickets_query(tenant_id, session)
            else:
                return self._get_tenant_tickets_query(tenant_id, session)
                
        except Exception as e:
            logger.error(f"Error getting tenant tickets: {e}")
            return []
    
    def _get_tenant_tickets_query(self, tenant_id, session):
        """Internal method to get tenant tickets"""
        # Get users for this tenant
        tenant_users = [user_id for user_id, t_id in self.user_tenant_mapping.items() if t_id == tenant_id]
        
        if not tenant_users:
            # If no specific users assigned, return all tickets for default tenant
            if tenant_id == 'default':
                return session.query(Ticket).all()
            else:
                return []
        
        return session.query(Ticket).filter(Ticket.user_id.in_(tenant_users)).all()
    
    def get_tenant_analytics(self, tenant_id):
        """Get analytics data for specific tenant"""
        try:
            with SessionLocal() as session:
                tenant_users = [user_id for user_id, t_id in self.user_tenant_mapping.items() if t_id == tenant_id]
                
                if not tenant_users and tenant_id != 'default':
                    return self._empty_analytics()
                
                # Get tickets for tenant users
                if tenant_users:
                    tickets_query = session.query(Ticket).filter(Ticket.user_id.in_(tenant_users))
                else:
                    tickets_query = session.query(Ticket)  # Default tenant gets all
                
                total_tickets = tickets_query.count()
                active_tickets = tickets_query.filter(Ticket.status.in_(['open', 'escalated'])).count()
                resolved_tickets = tickets_query.filter(Ticket.status.in_(['resolved', 'closed'])).count()
                
                # AI performance for tenant
                ai_attempts = session.query(func.sum(Ticket.ai_attempts)).filter(
                    Ticket.user_id.in_(tenant_users) if tenant_users else True
                ).scalar() or 0
                
                auto_escalated = tickets_query.filter(Ticket.auto_escalated == True).count()
                
                return {
                    'tenant_id': tenant_id,
                    'total_users': len(tenant_users) if tenant_users else 'all',
                    'total_tickets': total_tickets,
                    'active_tickets': active_tickets,
                    'resolved_tickets': resolved_tickets,
                    'ai_attempts': ai_attempts,
                    'auto_escalated': auto_escalated,
                    'success_rate': ((total_tickets - auto_escalated) / total_tickets * 100) if total_tickets > 0 else 100
                }
                
        except Exception as e:
            logger.error(f"Error getting tenant analytics: {e}")
            return self._empty_analytics()
    
    def _empty_analytics(self):
        """Return empty analytics structure"""
        return {
            'total_users': 0,
            'total_tickets': 0,
            'active_tickets': 0,
            'resolved_tickets': 0,
            'ai_attempts': 0,
            'auto_escalated': 0,
            'success_rate': 100
        }
    
    def create_tenant(self, tenant_id, config, admin_id):
        """Create new tenant"""
        try:
            if tenant_id in self.tenants:
                return False, "Tenant already exists"
            
            # Validate config
            required_fields = ['name', 'admin_ids']
            for field in required_fields:
                if field not in config:
                    return False, f"Missing required field: {field}"
            
            # Set defaults
            default_config = {
                'features': {
                    'ai_assistance': True,
                    'auto_renewals': False,
                    'analytics': True,
                    'notifications': True
                },
                'limits': {
                    'max_lists': 100,
                    'max_tickets_per_user': 20,
                    'max_users': 1000
                },
                'branding': {
                    'bot_name': f"{config['name']} Bot",
                    'primary_color': '#667eea',
                    'logo_url': None
                }
            }
            
            # Merge with provided config
            final_config = {**default_config, **config}
            self.tenants[tenant_id] = final_config
            
            # Log tenant creation
            with SessionLocal() as session:
                audit_log = AuditLog(
                    admin_id=admin_id,
                    action='create_tenant',
                    target_type='tenant',
                    target_id=0,
                    new_value=json.dumps(final_config),
                    details=json.dumps({'tenant_id': tenant_id}),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"Created tenant {tenant_id}")
            return True, "Tenant created successfully"
            
        except Exception as e:
            logger.error(f"Error creating tenant: {e}")
            return False, str(e)
    
    def update_tenant_config(self, tenant_id, config_updates, admin_id):
        """Update tenant configuration"""
        try:
            if tenant_id not in self.tenants:
                return False, "Tenant does not exist"
            
            old_config = self.tenants[tenant_id].copy()
            
            # Update configuration
            self.tenants[tenant_id].update(config_updates)
            
            # Log configuration update
            with SessionLocal() as session:
                audit_log = AuditLog(
                    admin_id=admin_id,
                    action='update_tenant_config',
                    target_type='tenant',
                    target_id=0,
                    old_value=json.dumps(old_config),
                    new_value=json.dumps(self.tenants[tenant_id]),
                    details=json.dumps({'tenant_id': tenant_id}),
                    timestamp=datetime.now(timezone.utc)
                )
                session.add(audit_log)
                session.commit()
            
            logger.info(f"Updated tenant {tenant_id} configuration")
            return True, "Tenant configuration updated"
            
        except Exception as e:
            logger.error(f"Error updating tenant config: {e}")
            return False, str(e)
    
    def check_tenant_limits(self, tenant_id, limit_type, current_count):
        """Check if tenant is within limits"""
        tenant_config = self.get_tenant_config(tenant_id)
        limits = tenant_config.get('limits', {})
        
        limit_value = limits.get(limit_type)
        if limit_value is None:
            return True, "No limit set"
        
        if current_count >= limit_value:
            return False, f"Limit exceeded: {current_count}/{limit_value}"
        
        return True, f"Within limits: {current_count}/{limit_value}"
    
    def get_tenant_branding(self, tenant_id):
        """Get branding configuration for tenant"""
        tenant_config = self.get_tenant_config(tenant_id)
        return tenant_config.get('branding', {
            'bot_name': 'ErixCast Bot',
            'primary_color': '#667eea',
            'logo_url': None
        })
    
    def is_feature_enabled(self, tenant_id, feature_name):
        """Check if feature is enabled for tenant"""
        tenant_config = self.get_tenant_config(tenant_id)
        features = tenant_config.get('features', {})
        return features.get(feature_name, False)
    
    def get_all_tenants(self):
        """Get all tenant configurations"""
        return self.tenants.copy()
    
    def get_tenant_users(self, tenant_id):
        """Get all users assigned to tenant"""
        return [user_id for user_id, t_id in self.user_tenant_mapping.items() if t_id == tenant_id]
    
    def get_tenant_stats(self):
        """Get statistics about all tenants"""
        stats = {}
        
        for tenant_id in self.tenants:
            tenant_users = self.get_tenant_users(tenant_id)
            tenant_analytics = self.get_tenant_analytics(tenant_id)
            
            stats[tenant_id] = {
                'name': self.tenants[tenant_id]['name'],
                'user_count': len(tenant_users),
                'ticket_count': tenant_analytics['total_tickets'],
                'active_tickets': tenant_analytics['active_tickets'],
                'features_enabled': len([f for f, enabled in self.tenants[tenant_id]['features'].items() if enabled])
            }
        
        return stats

# Global multi-tenant service instance
multi_tenant_service = MultiTenantService()
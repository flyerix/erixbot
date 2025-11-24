"""
Feature flag service for safe deployments and gradual rollouts
"""
import logging
import random
from typing import Dict, Any, Optional
from models import SessionLocal, FeatureFlag

logger = logging.getLogger(__name__)

class FeatureFlagService:
    def __init__(self):
        self.cache = {}  # Simple in-memory cache
        self.cache_ttl = 300  # 5 minutes cache TTL
        self.last_cache_update = 0

    def is_enabled(self, flag_name: str, user_id: Optional[int] = None) -> bool:
        """Check if a feature flag is enabled for a user"""
        flag = self._get_flag(flag_name)
        if not flag:
            return False

        if not flag.is_enabled:
            return False

        # Check rollout percentage
        if flag.rollout_percentage < 100.0:
            if user_id is None:
                # For anonymous users, use random rollout
                return random.random() * 100 < flag.rollout_percentage
            else:
                # For logged users, use consistent rollout based on user_id
                return (user_id % 100) < flag.rollout_percentage

        return True

    def get_flag_value(self, flag_name: str) -> Optional[Dict[str, Any]]:
        """Get complete feature flag information"""
        flag = self._get_flag(flag_name)
        if not flag:
            return None

        return {
            'name': flag.name,
            'is_enabled': flag.is_enabled,
            'rollout_percentage': flag.rollout_percentage,
            'description': flag.description,
            'created_at': flag.created_at.isoformat(),
            'updated_at': flag.updated_at.isoformat()
        }

    def create_flag(self, name: str, description: str = "", rollout_percentage: float = 0.0) -> bool:
        """Create a new feature flag"""
        session = SessionLocal()
        try:
            # Check if flag already exists
            existing = session.query(FeatureFlag).filter(FeatureFlag.name == name).first()
            if existing:
                logger.warning(f"Feature flag {name} already exists")
                return False

            flag = FeatureFlag(
                name=name,
                description=description,
                rollout_percentage=rollout_percentage,
                is_enabled=False
            )
            session.add(flag)
            session.commit()

            # Invalidate cache
            self._invalidate_cache()

            logger.info(f"Feature flag {name} created")
            return True
        except Exception as e:
            logger.error(f"Failed to create feature flag {name}: {e}")
            return False
        finally:
            session.close()

    def update_flag(self, name: str, is_enabled: Optional[bool] = None,
                   rollout_percentage: Optional[float] = None,
                   description: Optional[str] = None) -> bool:
        """Update an existing feature flag"""
        session = SessionLocal()
        try:
            flag = session.query(FeatureFlag).filter(FeatureFlag.name == name).first()
            if not flag:
                logger.warning(f"Feature flag {name} not found")
                return False

            if is_enabled is not None:
                flag.is_enabled = is_enabled
            if rollout_percentage is not None:
                flag.rollout_percentage = max(0.0, min(100.0, rollout_percentage))
            if description is not None:
                flag.description = description

            session.commit()

            # Invalidate cache
            self._invalidate_cache()

            logger.info(f"Feature flag {name} updated")
            return True
        except Exception as e:
            logger.error(f"Failed to update feature flag {name}: {e}")
            return False
        finally:
            session.close()

    def delete_flag(self, name: str) -> bool:
        """Delete a feature flag"""
        session = SessionLocal()
        try:
            flag = session.query(FeatureFlag).filter(FeatureFlag.name == name).first()
            if not flag:
                logger.warning(f"Feature flag {name} not found")
                return False

            session.delete(flag)
            session.commit()

            # Invalidate cache
            self._invalidate_cache()

            logger.info(f"Feature flag {name} deleted")
            return True
        except Exception as e:
            logger.error(f"Failed to delete feature flag {name}: {e}")
            return False
        finally:
            session.close()

    def list_flags(self) -> Dict[str, Dict[str, Any]]:
        """List all feature flags"""
        session = SessionLocal()
        try:
            flags = session.query(FeatureFlag).all()
            return {flag.name: {
                'is_enabled': flag.is_enabled,
                'rollout_percentage': flag.rollout_percentage,
                'description': flag.description,
                'created_at': flag.created_at.isoformat(),
                'updated_at': flag.updated_at.isoformat()
            } for flag in flags}
        finally:
            session.close()

    def _get_flag(self, name: str) -> Optional[FeatureFlag]:
        """Get feature flag from cache or database"""
        import time
        current_time = time.time()

        # Check cache validity
        if current_time - self.last_cache_update > self.cache_ttl:
            self._refresh_cache()

        return self.cache.get(name)

    def _refresh_cache(self) -> None:
        """Refresh the feature flags cache"""
        import time
        session = SessionLocal()
        try:
            flags = session.query(FeatureFlag).all()
            self.cache = {flag.name: flag for flag in flags}
            self.last_cache_update = time.time()
            logger.debug(f"Refreshed feature flags cache with {len(flags)} flags")
        finally:
            session.close()

    def _invalidate_cache(self) -> None:
        """Invalidate the cache"""
        import time
        self.last_cache_update = 0  # Force refresh on next access

# Global feature flag service instance
feature_flag_service = FeatureFlagService()

# Convenience functions for common feature checks
def is_feature_enabled(feature_name: str, user_id: Optional[int] = None) -> bool:
    """Check if a feature is enabled"""
    return feature_flag_service.is_enabled(feature_name, user_id)

def get_feature_flag(feature_name: str) -> Optional[Dict[str, Any]]:
    """Get feature flag details"""
    return feature_flag_service.get_flag_value(feature_name)

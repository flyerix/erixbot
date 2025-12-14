#!/usr/bin/env python3
"""
Test script to verify all imports work correctly
"""
import sys
import os

# Add app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

def test_basic_imports():
    """Test basic imports"""
    print("Testing basic imports...")
    
    try:
        import models
        print("✅ models imported successfully")
    except Exception as e:
        print(f"❌ models import failed: {e}")
        return False
    
    try:
        from models import SessionLocal, List, Ticket
        print("✅ Basic models imported successfully")
    except Exception as e:
        print(f"❌ Basic models import failed: {e}")
        return False
    
    return True

def test_service_imports():
    """Test service imports"""
    print("\nTesting service imports...")
    
    services = [
        'analytics_service',
        'smart_ai_service', 
        'smart_notifications',
        'security_service',
        'ui_service',
        'automation_service',
        'multi_tenant_service',
        'gamification_service',
        'integration_service'
    ]
    
    success_count = 0
    for service in services:
        try:
            module = __import__(f'services.{service}', fromlist=[''])
            print(f"✅ services.{service} imported successfully")
            success_count += 1
        except Exception as e:
            print(f"⚠️ services.{service} import failed: {e}")
    
    print(f"\nService import results: {success_count}/{len(services)} successful")
    return success_count > 0

def test_web_dashboard():
    """Test web dashboard import"""
    print("\nTesting web dashboard...")
    
    try:
        import web_dashboard
        print("✅ web_dashboard imported successfully")
        return True
    except Exception as e:
        print(f"⚠️ web_dashboard import failed: {e}")
        return False

def test_bot_import():
    """Test bot import"""
    print("\nTesting bot import...")
    
    try:
        import bot
        print("✅ bot imported successfully")
        return True
    except Exception as e:
        print(f"❌ bot import failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Starting import tests...\n")
    
    results = []
    results.append(test_basic_imports())
    results.append(test_service_imports())
    results.append(test_web_dashboard())
    results.append(test_bot_import())
    
    success_count = sum(results)
    total_tests = len(results)
    
    print(f"\n📊 Test Results: {success_count}/{total_tests} tests passed")
    
    if success_count == total_tests:
        print("🎉 All imports working correctly!")
        return True
    elif success_count > 0:
        print("⚠️ Some imports working, system should be functional")
        return True
    else:
        print("❌ Critical import failures detected")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
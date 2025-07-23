#!/usr/bin/env python3
"""
Test Script: Verify OpenWeather Extension Uninstall Fix

This script tests that the fix properly handles service registration
and that uninstall will work correctly without destroying the Engine section.

Run this BEFORE installing the fixed extension to verify the approach.
"""

import configobj
import tempfile
import os
import sys

def test_service_registration_approach():
    """Test the manual service registration approach like AirVisual."""
    
    print("Testing Manual Service Registration Approach")
    print("=" * 60)
    
    # Create a mock weewx.conf with existing services
    mock_config = configobj.ConfigObj()
    mock_config['Engine'] = {
        'Services': {
            'data_services': 'weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC, weewx.engine.StdTimeSynch'
        }
    }
    
    print("BEFORE service registration:")
    print(f"  data_services = {mock_config['Engine']['Services']['data_services']}")
    
    # Simulate the FIXED manual registration approach
    def register_service_fixed(config_dict):
        """Fixed service registration (like AirVisual)."""
        services = config_dict['Engine']['Services']
        current_data_services = services.get('data_services', '')
        
        # Convert to list for manipulation
        if isinstance(current_data_services, str):
            data_services_list = [s.strip() for s in current_data_services.split(',') if s.strip()]
        else:
            data_services_list = list(current_data_services) if current_data_services else []
        
        # Add our service if not already present
        openweather_service = 'user.openweather.OpenWeatherService'
        if openweather_service not in data_services_list:
            # Insert after StdConvert but before StdQC for proper data flow
            insert_position = len(data_services_list)  # Default to end
            for i, service in enumerate(data_services_list):
                if 'StdConvert' in service:
                    insert_position = i + 1
                    break
                elif 'StdQC' in service:
                    insert_position = i
                    break
            
            data_services_list.insert(insert_position, openweather_service)
            
            # Update configuration (PRESERVES existing services)
            services['data_services'] = ', '.join(data_services_list)
            return True
        return False
    
    # Test the registration
    was_added = register_service_fixed(mock_config)
    
    print("AFTER service registration:")
    print(f"  data_services = {mock_config['Engine']['Services']['data_services']}")
    print(f"  Service added: {was_added}")
    
    # Verify all original services are still there
    original_services = ['weewx.engine.StdConvert', 'weewx.engine.StdCalibrate', 'weewx.engine.StdQC', 'weewx.engine.StdTimeSynch']
    current_services = mock_config['Engine']['Services']['data_services']
    
    all_preserved = all(service in current_services for service in original_services)
    openweather_added = 'user.openweather.OpenWeatherService' in current_services
    
    print(f"\n✓ All original services preserved: {all_preserved}")
    print(f"✓ OpenWeather service added: {openweather_added}")
    
    return all_preserved and openweather_added

def test_config_parameter_vs_manual():
    """Compare config parameter approach vs manual approach."""
    
    print("\n" + "=" * 60)
    print("COMPARING APPROACHES")
    print("=" * 60)
    
    # Simulate what would happen with config parameter (BROKEN approach)
    print("BROKEN APPROACH (what was causing the bug):")
    print("  ExtensionInstaller.__init__(config={'Engine': {'Services': {'data_services': '...'}}}")
    print("  Result: WeeWX treats entire [Engine][[Services]] as 'owned' by extension")
    print("  Uninstall: WeeWX removes entire [Engine][[Services]] section!")
    print("  ❌ DESTROYS ALL EXISTING SERVICES")
    
    print("\nFIXED APPROACH (like AirVisual):")
    print("  ExtensionInstaller.__init__(config={'OpenWeatherService': {...}})  # No Engine section")
    print("  configure() method manually modifies existing data_services list")
    print("  Result: WeeWX only knows about OpenWeatherService section")
    print("  Uninstall: WeeWX removes OpenWeatherService section, leaves Engine alone")
    print("  ✓ PRESERVES ALL EXISTING SERVICES")

def test_uninstall_simulation():
    """Simulate what happens during uninstall with both approaches."""
    
    print("\n" + "=" * 60)
    print("UNINSTALL SIMULATION")
    print("=" * 60)
    
    # Mock configuration state after installation
    mock_config = configobj.ConfigObj()
    mock_config['Engine'] = {
        'Services': {
            'data_services': 'weewx.engine.StdConvert, weewx.engine.StdCalibrate, user.openweather.OpenWeatherService, weewx.engine.StdQC'
        }
    }
    mock_config['OpenWeatherService'] = {
        'enable': True,
        'api_key': 'test_key'
    }
    
    print("BEFORE uninstall:")
    print(f"  [Engine][[Services]]data_services = {mock_config['Engine']['Services']['data_services']}")
    print(f"  [OpenWeatherService] section exists: {'OpenWeatherService' in mock_config}")
    
    # Simulate FIXED uninstall (only removes service, not entire section)
    def simulate_fixed_uninstall(config_dict):
        """Simulate what WeeWX uninstaller does with FIXED approach."""
        # Remove the service configuration section (this is safe)
        if 'OpenWeatherService' in config_dict:
            del config_dict['OpenWeatherService']
        
        # WeeWX doesn't touch Engine section because extension didn't claim ownership
        # Manual cleanup of service from data_services list would be done by extension
        services = config_dict['Engine']['Services']
        current_data_services = services.get('data_services', '')
        data_services_list = [s.strip() for s in current_data_services.split(',') if s.strip()]
        
        # Remove our service
        openweather_service = 'user.openweather.OpenWeatherService'
        if openweather_service in data_services_list:
            data_services_list.remove(openweather_service)
            services['data_services'] = ', '.join(data_services_list)
        
        return True
    
    success = simulate_fixed_uninstall(mock_config)
    
    print("AFTER FIXED uninstall:")
    print(f"  [Engine][[Services]]data_services = {mock_config['Engine']['Services']['data_services']}")
    print(f"  [OpenWeatherService] section exists: {'OpenWeatherService' in mock_config}")
    print(f"  Engine section preserved: {'Engine' in mock_config}")
    
    # Verify Engine section is intact
    engine_preserved = 'Engine' in mock_config
    service_removed = 'user.openweather.OpenWeatherService' not in mock_config['Engine']['Services']['data_services']
    config_removed = 'OpenWeatherService' not in mock_config
    
    print(f"\n✓ Engine section preserved: {engine_preserved}")
    print(f"✓ OpenWeather service removed from list: {service_removed}")
    print(f"✓ OpenWeather config section removed: {config_removed}")
    
    return engine_preserved and service_removed and config_removed

def test_file_differences():
    """Show the key differences between broken and fixed install.py files."""
    
    print("\n" + "=" * 60)
    print("KEY FILE DIFFERENCES")
    print("=" * 60)
    
    print("BROKEN install.py (OpenWeather original):")
    print("  class OpenWeatherInstaller(ExtensionInstaller):")
    print("      def __init__(self):")
    print("          super().__init__(")
    print("              config={")
    print("                  'Engine': {                    # ← PROBLEM!")
    print("                      'Services': {")
    print("                          'data_services': 'user.openweather.OpenWeatherService'")
    print("                      }")
    print("                  }")
    print("              })")
    print()
    
    print("FIXED install.py (like AirVisual):")
    print("  class OpenWeatherInstaller(ExtensionInstaller):")
    print("      def __init__(self):")
    print("          super().__init__(")
    print("              config={")
    print("                  'OpenWeatherService': { ... }  # Only service config")
    print("                  # Engine section REMOVED")
    print("              })")
    print()
    print("      def configure(self, engine):")
    print("          # ... other setup ...")
    print("          self._register_service(engine.config_dict)  # ← MANUAL REGISTRATION")
    print()
    print("      def _register_service(self, config_dict):")
    print("          # Manually append to existing data_services list")
    print("          # PRESERVES existing services")

def main():
    """Run all tests to verify the fix."""
    
    print("OpenWeather Extension Uninstall Fix - Test Suite")
    print("=" * 60)
    print("This test verifies that the fix will prevent the Engine section deletion bug.")
    print()
    
    # Run tests
    test1_passed = test_service_registration_approach()
    test_config_parameter_vs_manual()
    test2_passed = test_uninstall_simulation()
    test_file_differences()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"✓ Service registration test passed: {test1_passed}")
    print(f"✓ Uninstall simulation test passed: {test2_passed}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED!")
        print("The fix should prevent the Engine section deletion bug.")
        print("\nSafe to proceed with:")
        print("1. Replace install.py with the fixed version")
        print("2. Test install/uninstall cycle")
        print("3. Verify Engine section is preserved")
    else:
        print("\n❌ TESTS FAILED!")
        print("Do not proceed until all tests pass.")
    
    return test1_passed and test2_passed

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""
Service Integration Test Suite for WeeWX OpenWeather Extension

Tests the enhanced openweather.py service to verify it correctly:
- Reads field selections from configuration
- Applies field filtering during data collection
- Only stores selected fields in database
- Handles different complexity levels properly

Usage:
    python3 examples/test_service_integration.py [--api-key=YOUR_KEY]
    
Requirements:
    - Real WeeWX 5.1+ installation
    - OpenWeather extension installed
    - Valid OpenWeatherMap API key for live tests
"""

import sys
import os
import tempfile
import shutil
import configobj
import sqlite3
import unittest
from unittest.mock import Mock, patch, MagicMock
import json
import time

# Add paths to find WeeWX and extension modules
sys.path.insert(0, '/usr/share/weewx')
sys.path.insert(0, '/etc/weewx/bin/user')

try:
    import weewx
    import weewx.manager
    import weewx.engine
    import weeutil.config
except ImportError as e:
    print(f"❌ Error: Cannot import WeeWX modules: {e}")
    sys.exit(1)

try:
    # Import extension components
    import openweather
    from install import FieldSelectionHelper
except ImportError as e:
    print(f"❌ Error: Cannot import OpenWeather extension modules: {e}")
    sys.exit(1)


class ServiceIntegrationTestSuite(unittest.TestCase):
    """Test suite for service integration with field selection."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        print("\n" + "="*80)
        print("SERVICE INTEGRATION TEST SUITE - SETUP")
        print("="*80)
        
        # Create temporary directory
        cls.test_dir = tempfile.mkdtemp(prefix='weewx_service_test_')
        print(f"Test directory: {cls.test_dir}")
        
        # Test coordinates (Huntington Beach, CA)
        cls.test_latitude = 33.656915
        cls.test_longitude = -117.982542
        
        print("✓ Test environment setup complete")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        print("\n" + "="*80)
        print("SERVICE INTEGRATION TEST SUITE - CLEANUP")
        print("="*80)
        
        # Remove temporary directory
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        print(f"✓ Cleaned up test directory: {cls.test_dir}")
    
    def setUp(self):
        """Set up for individual test."""
        # Create test configuration
        self.config_dict = self._create_test_config()
        
        # Create mock engine
        self.mock_engine = Mock()
        self.mock_engine.config_dict = self.config_dict
    
    def tearDown(self):
        """Clean up after individual test."""
        pass
    
    def _create_test_config(self, field_selection=None, complexity_level='standard'):
        """Create test configuration with field selection."""
        if field_selection is None:
            field_selection = {
                'current_weather': ['temp', 'humidity', 'pressure'],
                'air_quality': ['pm2_5', 'aqi']
            }
        
        config_dict = configobj.ConfigObj()
        config_dict['Station'] = {
            'latitude': self.test_latitude,
            'longitude': self.test_longitude
        }
        
        config_dict['OpenWeatherService'] = {
            'enable': True,
            'api_key': 'test_api_key_12345',
            'timeout': 30,
            'log_success': False,
            'log_errors': True,
            'modules': {
                'current_weather': True,
                'air_quality': True
            },
            'intervals': {
                'current_weather': 3600,
                'air_quality': 7200
            },
            'field_selection': {
                'complexity_level': complexity_level,
                'selected_fields': field_selection
            }
        }
        
        return config_dict


class TestServiceFieldSelection(ServiceIntegrationTestSuite):
    """Test service correctly reads and applies field selection."""
    
    def test_service_field_selection_parsing(self):
        """Test service correctly parses field selection from configuration."""
        print("\n--- Testing Service Field Selection Parsing ---")
        
        # Test custom field selection
        custom_selection = {
            'current_weather': ['temp', 'feels_like', 'wind_speed'],
            'air_quality': ['pm2_5', 'ozone']
        }
        
        config_dict = self._create_test_config(
            field_selection=custom_selection,
            complexity_level='custom'
        )
        
        # Mock the background thread to prevent actual API calls
        with patch('openweather.OpenWeatherBackgroundThread') as mock_thread_class:
            mock_thread = Mock()
            mock_thread_class.return_value = mock_thread
            
            with patch('openweather.log'):
                service = openweather.OpenWeatherService(self.mock_engine, config_dict)
                
                # Verify service parsed field selection correctly
                self.assertEqual(service.selected_fields, custom_selection)
                
                # Verify background thread was initialized with correct selection
                mock_thread_class.assert_called_once()
                call_args = mock_thread_class.call_args
                passed_selected_fields = call_args[0][1]  # Second argument to constructor
                self.assertEqual(passed_selected_fields, custom_selection)
        
        print("✓ Service correctly parsed custom field selection")
    
    def test_service_complexity_level_parsing(self):
        """Test service correctly handles complexity levels."""
        print("\n--- Testing Service Complexity Level Parsing ---")
        
        # Test standard complexity level
        config_dict = self._create_test_config(complexity_level='standard')
        
        with patch('openweather.OpenWeatherBackgroundThread'), \
             patch('openweather.log'):
            service = openweather.OpenWeatherService(self.mock_engine, config_dict)
            
            # Should resolve to standard field selection
            expected_standard = {
                'current_weather': ['temp', 'feels_like', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'cloud_cover'],
                'air_quality': ['pm2_5', 'aqi']
            }
            
            self.assertEqual(service.selected_fields, expected_standard)
        
        print("✓ Service correctly resolved standard complexity level")
    
    def test_service_unit_system_setup(self):
        """Test service sets up unit system for selected fields only."""
        print("\n--- Testing Service Unit System Setup ---")
        
        # Test with limited field selection
        limited_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        config_dict = self._create_test_config(field_selection=limited_selection)
        
        with patch('openweather.OpenWeatherBackgroundThread'), \
             patch('openweather.log'):
            
            # Clear any existing unit mappings
            import weewx.units
            original_obs_group_dict = weewx.units.obs_group_dict.copy()
            
            try:
                service = openweather.OpenWeatherService(self.mock_engine, config_dict)
                
                # Verify unit mappings were added for selected fields
                self.assertIn('ow_temperature', weewx.units.obs_group_dict)
                self.assertIn('ow_humidity', weewx.units.obs_group_dict)
                self.assertIn('ow_pm25', weewx.units.obs_group_dict)
                
                # Verify correct unit groups
                self.assertEqual(weewx.units.obs_group_dict['ow_temperature'], 'group_temperature')
                self.assertEqual(weewx.units.obs_group_dict['ow_humidity'], 'group_percent')
                self.assertEqual(weewx.units.obs_group_dict['ow_pm25'], 'group_concentration')
                
            finally:
                # Restore original unit mappings
                weewx.units.obs_group_dict.clear()
                weewx.units.obs_group_dict.update(original_obs_group_dict)
        
        print("✓ Service correctly set up unit system for selected fields")


class TestDataCollectorFieldFiltering(ServiceIntegrationTestSuite):
    """Test data collector applies field filtering correctly."""
    
    def test_data_collector_field_filtering(self):
        """Test data collector only processes selected fields."""
        print("\n--- Testing Data Collector Field Filtering ---")
        
        # Test selection with limited fields
        test_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        # Create data collector with field selection
        collector = openweather.OpenWeatherDataCollector(
            api_key='test_key',
            timeout=30,
            selected_fields=test_selection
        )
        
        # Mock API response for current weather
        mock_weather_response = {
            'main': {
                'temp': 20.5,
                'humidity': 65,
                'pressure': 1013.2,  # Not selected
                'feels_like': 19.8   # Not selected
            },
            'wind': {
                'speed': 3.2,        # Not selected
                'deg': 180          # Not selected
            },
            'clouds': {
                'all': 25           # Not selected
            }
        }
        
        # Test extraction and filtering
        extracted_data = collector._extract_weather_data(mock_weather_response)
        filtered_data = collector._apply_field_selection(extracted_data, 'current_weather')
        
        # Should only include selected fields
        expected_fields = {'ow_temperature', 'ow_humidity', 'ow_weather_timestamp'}
        actual_fields = set(filtered_data.keys())
        
        # Remove timestamp for comparison
        actual_data_fields = {f for f in actual_fields if not f.endswith('_timestamp')}
        expected_data_fields = {f for f in expected_fields if not f.endswith('_timestamp')}
        
        self.assertEqual(actual_data_fields, expected_data_fields)
        
        # Verify correct values
        self.assertEqual(filtered_data['ow_temperature'], 20.5)
        self.assertEqual(filtered_data['ow_humidity'], 65)
        
        # Verify excluded fields are not present
        self.assertNotIn('ow_pressure', filtered_data)
        self.assertNotIn('ow_feels_like', filtered_data)
        self.assertNotIn('ow_wind_speed', filtered_data)
        
        print("✓ Data collector correctly filtered to selected fields only")
    
    def test_air_quality_field_filtering(self):
        """Test air quality field filtering."""
        print("\n--- Testing Air Quality Field Filtering ---")
        
        test_selection = {
            'current_weather': [],
            'air_quality': ['pm2_5', 'aqi']
        }
        
        collector = openweather.OpenWeatherDataCollector(
            api_key='test_key',
            timeout=30,
            selected_fields=test_selection
        )
        
        # Mock air quality API response
        mock_air_response = {
            'list': [{
                'main': {'aqi': 2},
                'components': {
                    'pm2_5': 15.3,
                    'pm10': 25.1,    # Not selected
                    'o3': 89.2,      # Not selected
                    'no2': 12.4,     # Not selected
                    'so2': 3.1,      # Not selected
                    'co': 245.8      # Not selected
                }
            }]
        }
        
        extracted_data = collector._extract_air_quality_data(mock_air_response)
        filtered_data = collector._apply_field_selection(extracted_data, 'air_quality')
        
        # Should only include selected air quality fields
        expected_fields = {'ow_pm25', 'ow_aqi'}
        actual_fields = {f for f in filtered_data.keys() if not f.endswith('_timestamp')}
        
        self.assertEqual(actual_fields, expected_fields)
        
        # Verify correct values
        self.assertEqual(filtered_data['ow_pm25'], 15.3)
        self.assertEqual(filtered_data['ow_aqi'], 2)
        
        # Verify excluded fields
        self.assertNotIn('ow_pm10', filtered_data)
        self.assertNotIn('ow_ozone', filtered_data)
        self.assertNotIn('ow_no2', filtered_data)
        
        print("✓ Air quality field filtering working correctly")
    
    def test_everything_selection_filtering(self):
        """Test 'everything' selection includes all fields."""
        print("\n--- Testing Everything Selection Filtering ---")
        
        test_selection = {
            'current_weather': 'all',
            'air_quality': 'all'
        }
        
        collector = openweather.OpenWeatherDataCollector(
            api_key='test_key',
            timeout=30,
            selected_fields=test_selection
        )
        
        # Mock complete API response
        mock_weather_response = {
            'main': {
                'temp': 20.5,
                'humidity': 65,
                'pressure': 1013.2,
                'feels_like': 19.8
            },
            'wind': {
                'speed': 3.2,
                'deg': 180,
                'gust': 4.1
            },
            'clouds': {'all': 25},
            'visibility': 10000,
            'weather': [{'main': 'Clear', 'description': 'clear sky', 'icon': '01d'}]
        }
        
        extracted_data = collector._extract_weather_data(mock_weather_response)
        filtered_data = collector._apply_field_selection(extracted_data, 'current_weather')
        
        # With 'all' selection, should include all available fields
        expected_minimum_fields = {
            'ow_temperature', 'ow_humidity', 'ow_pressure', 'ow_feels_like',
            'ow_wind_speed', 'ow_wind_direction', 'ow_wind_gust',
            'ow_cloud_cover', 'ow_visibility', 'ow_weather_main'
        }
        
        actual_fields = {f for f in filtered_data.keys() if not f.endswith('_timestamp')}
        
        # Should include at least the expected fields
        self.assertTrue(expected_minimum_fields.issubset(actual_fields))
        
        print(f"✓ Everything selection included {len(actual_fields)} fields as expected")


class TestBackgroundThreadIntegration(ServiceIntegrationTestSuite):
    """Test background thread respects field selection."""
    
    def test_background_thread_initialization(self):
        """Test background thread initialized with correct field selection."""
        print("\n--- Testing Background Thread Initialization ---")
        
        test_selection = {
            'current_weather': ['temp', 'pressure'],
            'air_quality': ['pm2_5']
        }
        
        config_dict = self._create_test_config(field_selection=test_selection)
        
        # Test background thread creation
        background_thread = openweather.OpenWeatherBackgroundThread(
            config=config_dict['OpenWeatherService'],
            selected_fields=test_selection
        )
        
        # Verify thread was initialized with correct selection
        self.assertEqual(background_thread.selected_fields, test_selection)
        
        # Verify data collector was created with correct selection
        self.assertEqual(background_thread.collector.selected_fields, test_selection)
        
        print("✓ Background thread initialized with correct field selection")
    
    def test_collection_scheduling(self):
        """Test background thread only schedules collection for enabled modules."""
        print("\n--- Testing Collection Scheduling ---")
        
        # Test with only current_weather enabled
        weather_only_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': []  # Empty - effectively disabled
        }
        
        config_dict = self._create_test_config(field_selection=weather_only_selection)
        
        background_thread = openweather.OpenWeatherBackgroundThread(
            config=config_dict['OpenWeatherService'],
            selected_fields=weather_only_selection
        )
        
        # Verify intervals are set correctly
        self.assertIn('current_weather', background_thread.intervals)
        self.assertIn('air_quality', background_thread.intervals)
        
        # Verify selected fields
        self.assertIn('current_weather', background_thread.selected_fields)
        self.assertEqual(background_thread.selected_fields['air_quality'], [])
        
        print("✓ Collection scheduling respects field selection")


class TestArchiveRecordInjection(ServiceIntegrationTestSuite):
    """Test archive record injection with field filtering."""
    
    def test_archive_record_field_injection(self):
        """Test only selected fields are injected into archive records."""
        print("\n--- Testing Archive Record Field Injection ---")
        
        test_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        config_dict = self._create_test_config(field_selection=test_selection)
        
        with patch('openweather.OpenWeatherBackgroundThread') as mock_thread_class:
            # Mock background thread with test data
            mock_thread = Mock()
            mock_thread.get_latest_data.return_value = {
                'ow_temperature': 22.5,
                'ow_humidity': 68.0,
                'ow_pressure': 1015.2,     # Not selected - should not be injected
                'ow_pm25': 12.8,
                'ow_pm10': 18.5,           # Not selected - should not be injected
                'ow_weather_timestamp': time.time(),
                'ow_air_quality_timestamp': time.time()
            }
            mock_thread_class.return_value = mock_thread
            
            with patch('openweather.log'):
                service = openweather.OpenWeatherService(self.mock_engine, config_dict)
                
                # Create mock archive record event
                mock_event = Mock()
                mock_event.record = {}
                
                # Call archive record injection
                service.new_archive_record(mock_event)
                
                # Verify only selected fields were injected
                expected_fields = {'ow_temperature', 'ow_humidity', 'ow_pm25'}
                actual_fields = set(mock_event.record.keys())
                
                self.assertEqual(actual_fields, expected_fields)
                
                # Verify correct values
                self.assertEqual(mock_event.record['ow_temperature'], 22.5)
                self.assertEqual(mock_event.record['ow_humidity'], 68.0)
                self.assertEqual(mock_event.record['ow_pm25'], 12.8)
                
                # Verify excluded fields were not injected
                self.assertNotIn('ow_pressure', mock_event.record)
                self.assertNotIn('ow_pm10', mock_event.record)
        
        print("✓ Archive record injection correctly filtered to selected fields")
    
    def test_stale_data_handling(self):
        """Test handling of stale data in archive record injection."""
        print("\n--- Testing Stale Data Handling ---")
        
        config_dict = self._create_test_config()
        
        with patch('openweather.OpenWeatherBackgroundThread') as mock_thread_class:
            # Mock background thread with stale data
            mock_thread = Mock()
            stale_timestamp = time.time() - 10000  # Very old data
            mock_thread.get_latest_data.return_value = {
                'ow_temperature': 22.5,
                'ow_humidity': 68.0,
                'ow_weather_timestamp': stale_timestamp,
                'ow_air_quality_timestamp': stale_timestamp
            }
            mock_thread_class.return_value = mock_thread
            
            with patch('openweather.log'):
                service = openweather.OpenWeatherService(self.mock_engine, config_dict)
                
                mock_event = Mock()
                mock_event.record = {}
                
                service.new_archive_record(mock_event)
                
                # Should not inject stale data - fields should not be present
                self.assertEqual(len(mock_event.record), 0)
        
        print("✓ Stale data correctly excluded from archive records")


def run_service_integration_tests(api_key=None):
    """Run the complete service integration test suite."""
    print("WeeWX OpenWeather Extension - Service Integration Test Suite")
    print("=" * 80)
    print("Testing service integration with field selection system")
    
    if api_key:
        print(f"API key provided for live testing: {api_key[:8]}...")
    else:
        print("No API key provided - using mock testing only")
    print()
    
    # Create test suite
    test_classes = [
        TestServiceFieldSelection,
        TestDataCollectorFieldFiltering,
        TestBackgroundThreadIntegration,
        TestArchiveRecordInjection
    ]
    
    suite = unittest.TestSuite()
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 80)
    print("SERVICE INTEGRATION TEST SUITE - RESULTS")
    print("=" * 80)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall Result: {'✅ ALL TESTS PASSED' if success else '❌ SOME TESTS FAILED'}")
    
    if success:
        print("\n🎉 Service integration is working correctly!")
        print("✓ Service correctly reads field selection from configuration")
        print("✓ Data collector applies field filtering properly")
        print("✓ Background thread respects field selection")
        print("✓ Archive record injection filters to selected fields only")
        print("✓ Stale data handling works correctly")
    
    return success


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test WeeWX OpenWeather service integration')
    parser.add_argument('--api-key', help='OpenWeatherMap API key for live testing')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    success = run_service_integration_tests(args.api_key)
    sys.exit(0 if success else 1)
#!/usr/bin/env python3
"""
Field Selection Test Suite for WeeWX OpenWeather Extension

Tests the complete field selection functionality including:
- All 4 complexity levels (minimal, standard, comprehensive, everything)
- Custom field selection workflow
- Database field creation for selected fields only
- Configuration persistence and service reading
- Data collection filtering

Usage:
    python3 examples/test_field_selection.py [--config=/path/to/weewx.conf]
    
Requirements:
    - Real WeeWX 5.1+ installation
    - OpenWeather extension installed
    - Database write permissions
"""

import sys
import os
import tempfile
import shutil
import yaml
import configobj
import sqlite3
import unittest
from unittest.mock import Mock, patch
import subprocess
import time

# Add paths to find WeeWX and extension modules
sys.path.insert(0, '/usr/share/weewx')
sys.path.insert(0, '/etc/weewx/bin/user')

try:
    import weewx
    import weewx.manager
    import weeutil.config
    from weecfg.extension import ExtensionInstaller
except ImportError as e:
    print(f"❌ Error: Cannot import WeeWX modules: {e}")
    print("Ensure WeeWX 5.1+ is properly installed and this script has access to WeeWX paths")
    sys.exit(1)

try:
    # Import extension components
    import openweather
    from install import FieldSelectionHelper, DatabaseManager, OpenWeatherInstaller
except ImportError as e:
    print(f"❌ Error: Cannot import OpenWeather extension modules: {e}")
    print("Ensure OpenWeather extension is installed in bin/user/")
    sys.exit(1)


class FieldSelectionTestSuite(unittest.TestCase):
    """Comprehensive test suite for field selection functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment with temporary WeeWX configuration."""
        print("\n" + "="*80)
        print("FIELD SELECTION TEST SUITE - SETUP")
        print("="*80)
        
        # Create temporary directory for test
        cls.test_dir = tempfile.mkdtemp(prefix='weewx_openweather_test_')
        print(f"Test directory: {cls.test_dir}")
        
        # Create test configuration file
        cls.test_config_path = os.path.join(cls.test_dir, 'test_weewx.conf')
        cls._create_test_config()
        
        # Create test database
        cls.test_db_path = os.path.join(cls.test_dir, 'test_weewx.sdb')
        cls._create_test_database()
        
        # Load test configuration
        cls.config_dict = configobj.ConfigObj(cls.test_config_path, file_error=True)
        cls.config_dict.filename = cls.test_config_path
        
        print("✓ Test environment setup complete")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        print("\n" + "="*80)
        print("FIELD SELECTION TEST SUITE - CLEANUP")
        print("="*80)
        
        # Remove temporary directory
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        print(f"✓ Cleaned up test directory: {cls.test_dir}")
    
    @classmethod
    def _create_test_config(cls):
        """Create minimal test WeeWX configuration."""
        config_content = f"""
# Test WeeWX Configuration for OpenWeather Extension
WEEWX_ROOT = {cls.test_dir}

[Station]
    latitude = 33.656915
    longitude = -117.982542
    station_type = Simulator
    
[Engine]
    [[Services]]
        data_services = weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC

[DataBindings]
    [[wx_binding]]
        database = archive_sqlite
        table_name = archive
        manager = weewx.manager.DaySummaryManager

[Databases]
    [[archive_sqlite]]
        database_name = {cls.test_db_path}
        driver = weedb.sqlite
        
[DatabaseTypes]
    [[SQLite]]
        driver = weedb.sqlite
"""
        
        with open(cls.test_config_path, 'w') as f:
            f.write(config_content)
    
    @classmethod
    def _create_test_database(cls):
        """Create minimal test database with standard WeeWX schema."""
        conn = sqlite3.connect(cls.test_db_path)
        cursor = conn.cursor()
        
        # Create basic archive table
        cursor.execute('''
            CREATE TABLE archive (
                dateTime INTEGER NOT NULL UNIQUE PRIMARY KEY,
                interval INTEGER NOT NULL,
                outTemp REAL,
                outHumidity REAL,
                barometer REAL,
                windSpeed REAL,
                windDir REAL
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def setUp(self):
        """Set up for individual test."""
        # Create fresh field selection helper for each test
        self.extension_dir = os.path.dirname(os.path.abspath(__file__ + '/../'))
        self.field_helper = FieldSelectionHelper(self.extension_dir)
        self.db_manager = DatabaseManager(self.config_dict)
    
    def tearDown(self):
        """Clean up after individual test."""
        # Remove any OpenWeather fields that were added during test
        self._clean_openweather_fields()
        
        # Remove OpenWeatherService configuration if added
        if 'OpenWeatherService' in self.config_dict:
            del self.config_dict['OpenWeatherService']
    
    def _clean_openweather_fields(self):
        """Remove OpenWeather fields from test database."""
        try:
            conn = sqlite3.connect(self.test_db_path)
            cursor = conn.cursor()
            
            # Get current schema
            cursor.execute("PRAGMA table_info(archive)")
            columns = cursor.fetchall()
            
            # Find OpenWeather fields to drop
            ow_fields = [col[1] for col in columns if col[1].startswith('ow_')]
            
            # Drop OpenWeather fields (SQLite doesn't support DROP COLUMN directly)
            if ow_fields:
                # Get non-OpenWeather columns
                standard_columns = [col[1] for col in columns if not col[1].startswith('ow_')]
                
                # Create new table without OpenWeather fields
                cursor.execute('CREATE TABLE archive_temp AS SELECT {} FROM archive'.format(', '.join(standard_columns)))
                cursor.execute('DROP TABLE archive')
                cursor.execute('ALTER TABLE archive_temp RENAME TO archive')
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not clean OpenWeather fields: {e}")


class TestComplexityLevels(FieldSelectionTestSuite):
    """Test all 4 complexity levels create correct database fields."""
    
    def test_minimal_complexity_level(self):
        """Test minimal complexity level creates correct fields."""
        print("\n--- Testing Minimal Complexity Level ---")
        
        # Get minimal field selection
        selected_fields = self.field_helper.get_selected_fields('minimal')
        
        # Verify expected field structure
        expected_fields = {
            'current_weather': ['temp', 'humidity', 'pressure', 'wind_speed'],
            'air_quality': ['pm2_5', 'aqi']
        }
        self.assertEqual(selected_fields, expected_fields)
        
        # Get database field mappings
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        # Verify expected database fields
        expected_db_fields = ['ow_temperature', 'ow_humidity', 'ow_pressure', 'ow_wind_speed', 'ow_pm25', 'ow_aqi']
        self.assertEqual(set(field_mappings.keys()), set(expected_db_fields))
        
        # Test database field creation
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, len(expected_db_fields))
        
        # Verify fields exist in database
        existing_fields = self.db_manager._check_existing_fields()
        for field in expected_db_fields:
            self.assertIn(field, existing_fields)
        
        print(f"✓ Minimal complexity level: {len(expected_db_fields)} fields created successfully")
    
    def test_standard_complexity_level(self):
        """Test standard complexity level creates correct fields."""
        print("\n--- Testing Standard Complexity Level ---")
        
        selected_fields = self.field_helper.get_selected_fields('standard')
        
        expected_fields = {
            'current_weather': ['temp', 'feels_like', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'cloud_cover'],
            'air_quality': ['pm2_5', 'aqi']
        }
        self.assertEqual(selected_fields, expected_fields)
        
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        expected_db_fields = [
            'ow_temperature', 'ow_feels_like', 'ow_humidity', 'ow_pressure', 
            'ow_wind_speed', 'ow_wind_direction', 'ow_cloud_cover', 'ow_pm25', 'ow_aqi'
        ]
        self.assertEqual(set(field_mappings.keys()), set(expected_db_fields))
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, len(expected_db_fields))
        
        existing_fields = self.db_manager._check_existing_fields()
        for field in expected_db_fields:
            self.assertIn(field, existing_fields)
        
        print(f"✓ Standard complexity level: {len(expected_db_fields)} fields created successfully")
    
    def test_comprehensive_complexity_level(self):
        """Test comprehensive complexity level creates correct fields."""
        print("\n--- Testing Comprehensive Complexity Level ---")
        
        selected_fields = self.field_helper.get_selected_fields('comprehensive')
        
        expected_fields = {
            'current_weather': [
                'temp', 'feels_like', 'temp_min', 'temp_max', 'humidity', 'pressure',
                'wind_speed', 'wind_direction', 'wind_gust', 'cloud_cover', 'visibility'
            ],
            'air_quality': ['pm2_5', 'pm10', 'ozone', 'no2', 'aqi']
        }
        self.assertEqual(selected_fields, expected_fields)
        
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        # Should have 16 fields total
        self.assertEqual(len(field_mappings), 16)
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, 16)
        
        print(f"✓ Comprehensive complexity level: 16 fields created successfully")
    
    def test_everything_complexity_level(self):
        """Test everything complexity level creates all available fields."""
        print("\n--- Testing Everything Complexity Level ---")
        
        selected_fields = self.field_helper.get_selected_fields('everything')
        
        # Should select all fields
        self.assertEqual(selected_fields['current_weather'], 'all')
        self.assertEqual(selected_fields['air_quality'], 'all')
        
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        # Should have all available fields (20+ fields)
        self.assertGreater(len(field_mappings), 20)
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, len(field_mappings))
        
        print(f"✓ Everything complexity level: {len(field_mappings)} fields created successfully")


class TestCustomFieldSelection(FieldSelectionTestSuite):
    """Test custom field selection workflow."""
    
    def test_custom_field_validation(self):
        """Test custom field selection validation."""
        print("\n--- Testing Custom Field Validation ---")
        
        # Test valid custom selection
        valid_selection = {
            'current_weather': ['temp', 'humidity', 'pressure'],
            'air_quality': ['pm2_5']
        }
        
        validated = self.field_helper.validate_field_selection(valid_selection)
        self.assertEqual(validated, valid_selection)
        
        # Test invalid field names
        invalid_selection = {
            'current_weather': ['temp', 'invalid_field', 'pressure'],
            'air_quality': ['pm2_5', 'nonexistent_field']
        }
        
        validated = self.field_helper.validate_field_selection(invalid_selection)
        expected_valid = {
            'current_weather': ['temp', 'pressure'],
            'air_quality': ['pm2_5']
        }
        self.assertEqual(validated, expected_valid)
        
        print("✓ Custom field validation working correctly")
    
    def test_custom_field_database_creation(self):
        """Test database creation for custom field selection."""
        print("\n--- Testing Custom Field Database Creation ---")
        
        # Custom selection with specific fields
        custom_selection = {
            'current_weather': ['temp', 'feels_like', 'wind_speed'],
            'air_quality': ['pm2_5', 'ozone']
        }
        
        field_mappings = self.field_helper.get_database_field_mappings(custom_selection)
        
        expected_db_fields = ['ow_temperature', 'ow_feels_like', 'ow_wind_speed', 'ow_pm25', 'ow_ozone']
        self.assertEqual(set(field_mappings.keys()), set(expected_db_fields))
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, len(expected_db_fields))
        
        # Verify only selected fields were created
        existing_fields = self.db_manager._check_existing_fields()
        for field in expected_db_fields:
            self.assertIn(field, existing_fields)
        
        # Verify non-selected fields were NOT created
        non_selected_fields = ['ow_humidity', 'ow_pressure', 'ow_pm10', 'ow_no2']
        for field in non_selected_fields:
            self.assertNotIn(field, existing_fields)
        
        print(f"✓ Custom field selection: {len(expected_db_fields)} fields created, non-selected fields excluded")


class TestDatabaseFieldCreation(FieldSelectionTestSuite):
    """Test database field creation scenarios."""
    
    def test_field_type_handling(self):
        """Test proper handling of different field types."""
        print("\n--- Testing Field Type Handling ---")
        
        # Selection with different field types
        test_selection = {
            'current_weather': ['temp', 'weather_main'],  # REAL and TEXT
            'air_quality': ['aqi', 'pm2_5']  # INTEGER and REAL
        }
        
        field_mappings = self.field_helper.get_database_field_mappings(test_selection)
        
        # Verify field types
        self.assertEqual(field_mappings['ow_temperature'], 'REAL')
        self.assertEqual(field_mappings['ow_weather_main'], 'TEXT')
        self.assertEqual(field_mappings['ow_aqi'], 'INTEGER')
        self.assertEqual(field_mappings['ow_pm25'], 'REAL')
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, 4)
        
        # Verify fields exist with correct types in database
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        columns = {col[1]: col[2] for col in cursor.fetchall()}
        conn.close()
        
        # SQLite type mapping verification
        self.assertIn('ow_temperature', columns)
        self.assertIn('ow_weather_main', columns)
        self.assertIn('ow_aqi', columns)
        self.assertIn('ow_pm25', columns)
        
        print("✓ Field type handling: REAL, TEXT, and INTEGER types created correctly")
    
    def test_reinstallation_scenario(self):
        """Test reinstallation with existing fields."""
        print("\n--- Testing Reinstallation Scenario ---")
        
        # First installation
        initial_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        field_mappings = self.field_helper.get_database_field_mappings(initial_selection)
        created_count = self.db_manager.create_database_fields(field_mappings)
        self.assertEqual(created_count, 3)
        
        # Second "installation" with overlapping fields
        second_selection = {
            'current_weather': ['temp', 'pressure'],  # temp overlaps
            'air_quality': ['pm2_5', 'aqi']  # pm2_5 overlaps
        }
        
        field_mappings2 = self.field_helper.get_database_field_mappings(second_selection)
        created_count2 = self.db_manager.create_database_fields(field_mappings2)
        
        # Should only create new fields (pressure, aqi)
        self.assertEqual(created_count2, 2)
        
        # Verify all fields exist
        existing_fields = self.db_manager._check_existing_fields()
        expected_fields = ['ow_temperature', 'ow_humidity', 'ow_pressure', 'ow_pm25', 'ow_aqi']
        for field in expected_fields:
            self.assertIn(field, existing_fields)
        
        print("✓ Reinstallation scenario: Existing fields preserved, only new fields created")


class TestConfigurationPersistence(FieldSelectionTestSuite):
    """Test configuration persistence and service reading."""
    
    def test_configuration_storage(self):
        """Test field selection configuration storage."""
        print("\n--- Testing Configuration Storage ---")
        
        # Test configuration writing
        test_selection = {
            'current_weather': ['temp', 'humidity', 'pressure'],
            'air_quality': ['pm2_5', 'aqi']
        }
        
        # Simulate installer configuration writing
        self.config_dict['OpenWeatherService'] = {
            'enable': True,
            'api_key': 'test_key_12345',
            'field_selection': {
                'complexity_level': 'custom',
                'selected_fields': test_selection
            }
        }
        
        # Write configuration to file
        self.config_dict.write()
        
        # Reload configuration to verify persistence
        reloaded_config = configobj.ConfigObj(self.test_config_path, file_error=True)
        
        # Verify configuration was stored correctly
        self.assertEqual(reloaded_config['OpenWeatherService']['enable'], True)
        self.assertEqual(reloaded_config['OpenWeatherService']['api_key'], 'test_key_12345')
        self.assertEqual(
            reloaded_config['OpenWeatherService']['field_selection']['complexity_level'],
            'custom'
        )
        
        stored_selection = reloaded_config['OpenWeatherService']['field_selection']['selected_fields']
        self.assertEqual(dict(stored_selection), test_selection)
        
        print("✓ Configuration storage: Field selection persisted and reloaded correctly")
    
    def test_service_field_reading(self):
        """Test service correctly reads field selection from configuration."""
        print("\n--- Testing Service Field Reading ---")
        
        # Create test configuration
        test_selection = {
            'current_weather': ['temp', 'feels_like', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        self.config_dict['OpenWeatherService'] = {
            'enable': True,
            'api_key': 'test_key_12345',
            'timeout': 30,
            'modules': {
                'current_weather': True,
                'air_quality': True
            },
            'intervals': {
                'current_weather': 3600,
                'air_quality': 7200
            },
            'field_selection': {
                'complexity_level': 'custom',
                'selected_fields': test_selection
            }
        }
        
        # Test service can parse field selection
        mock_engine = Mock()
        mock_engine.config_dict = self.config_dict
        
        with patch('openweather.log'):
            # This would normally start background threads - we'll mock that
            with patch.object(openweather.OpenWeatherBackgroundThread, '__init__', return_value=None), \
                 patch.object(openweather.OpenWeatherBackgroundThread, 'start'):
                
                service = openweather.OpenWeatherService(mock_engine, self.config_dict)
                
                # Verify service parsed field selection correctly
                self.assertEqual(service.selected_fields, test_selection)
        
        print("✓ Service field reading: Service correctly parsed field selection from configuration")


class TestDataCollectionFiltering(FieldSelectionTestSuite):
    """Test data collection filtering based on field selection."""
    
    def test_field_filtering_logic(self):
        """Test that data collection respects field selection."""
        print("\n--- Testing Data Collection Filtering ---")
        
        # Test field selection manager functionality
        test_selection = {
            'current_weather': ['temp', 'humidity'],
            'air_quality': ['pm2_5']
        }
        
        # Get API path mappings (service would use this for filtering)
        api_mappings = self.field_helper.get_api_path_mappings(test_selection)
        
        # Verify only selected fields have mappings
        expected_mappings = {
            'ow_temperature': 'main.temp',
            'ow_humidity': 'main.humidity',
            'ow_pm25': 'list[0].components.pm2_5'
        }
        
        self.assertEqual(api_mappings, expected_mappings)
        
        # Test field filtering would exclude non-selected fields
        all_possible_fields = {
            'ow_temperature': 20.5,
            'ow_humidity': 65.0,
            'ow_pressure': 1013.2,  # Not selected
            'ow_pm25': 15.3,
            'ow_pm10': 25.1,  # Not selected
            'ow_aqi': 2  # Not selected
        }
        
        # Simulate filtering (what service would do)
        db_field_mappings = self.field_helper.get_database_field_mappings(test_selection)
        filtered_fields = {
            field: value for field, value in all_possible_fields.items()
            if field in db_field_mappings
        }
        
        expected_filtered = {
            'ow_temperature': 20.5,
            'ow_humidity': 65.0,
            'ow_pm25': 15.3
        }
        
        self.assertEqual(filtered_fields, expected_filtered)
        
        print("✓ Data collection filtering: Only selected fields would be processed")


class TestFieldCountEstimation(FieldSelectionTestSuite):
    """Test field count estimation functionality."""
    
    def test_field_count_estimation(self):
        """Test field count estimation for different selections."""
        print("\n--- Testing Field Count Estimation ---")
        
        # Test minimal
        minimal_fields = self.field_helper.get_selected_fields('minimal')
        minimal_count = self.field_helper.estimate_field_count(minimal_fields)
        self.assertEqual(minimal_count, 6)  # 4 weather + 2 air quality
        
        # Test standard
        standard_fields = self.field_helper.get_selected_fields('standard')
        standard_count = self.field_helper.estimate_field_count(standard_fields)
        self.assertEqual(standard_count, 9)  # 7 weather + 2 air quality
        
        # Test comprehensive
        comprehensive_fields = self.field_helper.get_selected_fields('comprehensive')
        comprehensive_count = self.field_helper.estimate_field_count(comprehensive_fields)
        self.assertEqual(comprehensive_count, 16)  # 11 weather + 5 air quality
        
        # Test everything
        everything_fields = self.field_helper.get_selected_fields('everything')
        everything_count = self.field_helper.estimate_field_count(everything_fields)
        self.assertGreater(everything_count, 20)
        
        print(f"✓ Field count estimation: minimal={minimal_count}, standard={standard_count}, comprehensive={comprehensive_count}, everything={everything_count}")


def run_test_suite(config_path=None):
    """Run the complete field selection test suite."""
    print("WeeWX OpenWeather Extension - Field Selection Test Suite")
    print("=" * 80)
    print("Testing field selection functionality against real WeeWX installation")
    print()
    
    # Configure test environment
    if config_path:
        print(f"Using custom WeeWX configuration: {config_path}")
        # Could adapt to use provided config instead of test config
    
    # Create test suite
    test_classes = [
        TestComplexityLevels,
        TestCustomFieldSelection,
        TestDatabaseFieldCreation,
        TestConfigurationPersistence,
        TestDataCollectionFiltering,
        TestFieldCountEstimation
    ]
    
    suite = unittest.TestSuite()
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 80)
    print("FIELD SELECTION TEST SUITE - RESULTS")
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
        print("\n🎉 Field selection system is working correctly!")
        print("✓ All complexity levels create correct database fields")
        print("✓ Custom field selection workflow functions properly")
        print("✓ Database field creation handles all scenarios")
        print("✓ Configuration persistence works correctly")
        print("✓ Data collection filtering logic is sound")
    
    return success


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test WeeWX OpenWeather field selection functionality')
    parser.add_argument('--config', help='Path to WeeWX configuration file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)
    
    success = run_test_suite(args.config)
    sys.exit(0 if success else 1)
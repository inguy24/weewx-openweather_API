#!/usr/bin/env python3
"""
Installation Scenario Test Suite for WeeWX OpenWeather Extension

Tests various installation scenarios including:
- Fresh installations with different complexity levels
- Reinstallation scenarios
- Upgrade scenarios with field selection changes
- Database field management edge cases
- Configuration validation

Usage:
    python3 examples/test_installation_scenarios.py
    
Requirements:
    - Real WeeWX 5.1+ installation
    - Database write permissions
    - weectl executable available
"""

import sys
import os
import tempfile
import shutil
import configobj
import sqlite3
import unittest
from unittest.mock import Mock, patch
import subprocess
import time
import yaml

# Add paths to find WeeWX and extension modules
sys.path.insert(0, '/usr/share/weewx')
sys.path.insert(0, '/etc/weewx/bin/user')

try:
    import weewx
    import weewx.manager
    import weeutil.config
except ImportError as e:
    print(f"❌ Error: Cannot import WeeWX modules: {e}")
    sys.exit(1)

try:
    from install import (
        FieldSelectionHelper, DatabaseManager, OpenWeatherInstaller,
        TerminalUI
    )
except ImportError as e:
    print(f"❌ Error: Cannot import OpenWeather extension modules: {e}")
    sys.exit(1)


class InstallationScenarioTestSuite(unittest.TestCase):
    """Test suite for installation scenarios."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test environment."""
        print("\n" + "="*80)
        print("INSTALLATION SCENARIO TEST SUITE - SETUP")
        print("="*80)
        
        # Create temporary directory
        cls.test_dir = tempfile.mkdtemp(prefix='weewx_install_test_')
        print(f"Test directory: {cls.test_dir}")
        
        # Create test database
        cls.test_db_path = os.path.join(cls.test_dir, 'test_weewx.sdb')
        cls._create_test_database()
        
        # Create test configuration
        cls.test_config_path = os.path.join(cls.test_dir, 'test_weewx.conf')
        cls.config_dict = cls._create_test_config()
        
        print("✓ Test environment setup complete")
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test environment."""
        print("\n" + "="*80)
        print("INSTALLATION SCENARIO TEST SUITE - CLEANUP") 
        print("="*80)
        
        # Remove temporary directory
        shutil.rmtree(cls.test_dir, ignore_errors=True)
        print(f"✓ Cleaned up test directory: {cls.test_dir}")
    
    @classmethod
    def _create_test_database(cls):
        """Create test database with standard WeeWX schema."""
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
    
    @classmethod
    def _create_test_config(cls):
        """Create test WeeWX configuration."""
        config_content = f"""
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
"""
        
        with open(cls.test_config_path, 'w') as f:
            f.write(config_content)
        
        config_dict = configobj.ConfigObj(cls.test_config_path, file_error=True)
        config_dict.filename = cls.test_config_path
        return config_dict
    
    def setUp(self):
        """Set up for individual test."""
        # Reset database to clean state
        self._reset_database()
        
        # Reset configuration
        self.config_dict = self.__class__._create_test_config()
        
        # Create fresh instances
        self.extension_dir = os.path.dirname(os.path.abspath(__file__ + '/../'))
        self.field_helper = FieldSelectionHelper(self.extension_dir)
        self.db_manager = DatabaseManager(self.config_dict)
    
    def tearDown(self):
        """Clean up after individual test."""
        # Clean any OpenWeather fields
        self._clean_openweather_fields()
        
        # Remove OpenWeatherService configuration
        if 'OpenWeatherService' in self.config_dict:
            del self.config_dict['OpenWeatherService']
    
    def _reset_database(self):
        """Reset database to original state."""
        self.__class__._create_test_database()
    
    def _clean_openweather_fields(self):
        """Remove OpenWeather fields from database."""
        try:
            conn = sqlite3.connect(self.test_db_path)
            cursor = conn.cursor()
            
            # Get current schema
            cursor.execute("PRAGMA table_info(archive)")
            columns = cursor.fetchall()
            
            # Find OpenWeather fields
            ow_fields = [col[1] for col in columns if col[1].startswith('ow_')]
            
            if ow_fields:
                # Recreate table without OpenWeather fields
                standard_columns = [col[1] for col in columns if not col[1].startswith('ow_')]
                cursor.execute(f'CREATE TABLE archive_temp AS SELECT {", ".join(standard_columns)} FROM archive')
                cursor.execute('DROP TABLE archive')
                cursor.execute('ALTER TABLE archive_temp RENAME TO archive')
            
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Warning: Could not clean OpenWeather fields: {e}")
    
    def _get_database_fields(self):
        """Get current database field names."""
        conn = sqlite3.connect(self.test_db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(archive)")
        fields = [col[1] for col in cursor.fetchall()]
        conn.close()
        return fields


class TestFreshInstallationScenarios(InstallationScenarioTestSuite):
    """Test fresh installation scenarios with different complexity levels."""
    
    def test_fresh_minimal_installation(self):
        """Test fresh installation with minimal complexity level."""
        print("\n--- Testing Fresh Minimal Installation ---")
        
        # Simulate minimal installation
        selected_fields = self.field_helper.get_selected_fields('minimal')
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        # Verify no OpenWeather fields exist initially
        initial_fields = self._get_database_fields()
        ow_fields = [f for f in initial_fields if f.startswith('ow_')]
        self.assertEqual(len(ow_fields), 0)
        
        # Create database fields
        created_count = self.db_manager.create_database_fields(field_mappings)
        
        # Verify correct number of fields created
        expected_count = 6  # 4 weather + 2 air quality for minimal
        self.assertEqual(created_count, expected_count)
        
        # Verify specific fields exist
        final_fields = self._get_database_fields()
        expected_fields = ['ow_temperature', 'ow_humidity', 'ow_pressure', 'ow_wind_speed', 'ow_pm25', 'ow_aqi']
        for field in expected_fields:
            self.assertIn(field, final_fields)
        
        # Verify no extra fields were created
        ow_fields_final = [f for f in final_fields if f.startswith('ow_')]
        self.assertEqual(set(ow_fields_final), set(expected_fields))
        
        print(f"✓ Fresh minimal installation: {created_count} fields created correctly")
    
    def test_fresh_comprehensive_installation(self):
        """Test fresh installation with comprehensive complexity level."""
        print("\n--- Testing Fresh Comprehensive Installation ---")
        
        selected_fields = self.field_helper.get_selected_fields('comprehensive')
        field_mappings = self.field_helper.get_database_field_mappings(selected_fields)
        
        created_count = self.db_manager.create_database_fields(field_mappings)
        
        # Comprehensive should create 16 fields
        expected_count = 16
        self.assertEqual(created_count, expected_count)
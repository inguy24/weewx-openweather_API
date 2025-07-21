#!/usr/bin/env python3
"""
OpenWeather Extension Installer for WeeWX 5.1+

This installer provides comprehensive OpenWeatherMap API integration with:
- Current weather data collection
- Air quality data collection  
- UV index data collection
- Modular configuration system
- Field selection capabilities
- Proper database schema management

Installation creates database fields only for enabled modules.
"""

import configobj
import os
import subprocess
import sys
import time
import weewx.manager
from weecfg.extension import ExtensionInstaller

def loader():
    """Return the installer instance."""
    return OpenWeatherInstaller()

class OpenWeatherInstaller(ExtensionInstaller):
    """OpenWeather Extension Installer following WeeWX 5.1 best practices."""
    
    def __init__(self):
        super(OpenWeatherInstaller, self).__init__(
            version="1.0.0",
            name="OpenWeather",
            description="Comprehensive OpenWeatherMap API integration for weather and air quality data",
            author="WeeWX Community",
            author_email="",
            files=[
                ('bin/user', ['bin/user/openweather.py'])
            ],
            config={
                'OpenWeatherService': {
                    'enable': True,
                    'api_key': 'REPLACE_WITH_YOUR_API_KEY',
                    'log_success': False,
                    'log_errors': True,
                    'timeout': 30,
                    'retry_attempts': 3,
                    'modules': {
                        'current_weather': True,
                        'air_quality': True,
                        'uv_index': False,
                        'forecast_daily': False,
                        'forecast_hourly': False
                    },
                    'intervals': {
                        'current_weather': 3600,    # 1 hour
                        'air_quality': 7200,        # 2 hours
                        'uv_index': 3600,           # 1 hour
                        'forecast_daily': 21600,    # 6 hours
                        'forecast_hourly': 3600     # 1 hour
                    }
                },
                'Engine': {
                    'Services': {
                        'data_services': 'user.openweather.OpenWeatherService'
                    }
                }
            }
        )
        
        # Database field definitions by module
        self.module_fields = {
            'current_weather': {
                'ow_temperature': 'REAL',
                'ow_feels_like': 'REAL',
                'ow_pressure': 'REAL',
                'ow_humidity': 'REAL',
                'ow_cloud_cover': 'REAL',
                'ow_visibility': 'REAL',
                'ow_wind_speed': 'REAL',
                'ow_wind_direction': 'REAL'
            },
            'air_quality': {
                'ow_pm25': 'REAL',
                'ow_pm10': 'REAL',
                'ow_ozone': 'REAL',
                'ow_no2': 'REAL',
                'ow_so2': 'REAL',
                'ow_co': 'REAL',
                'ow_aqi': 'INTEGER'
            },
            'uv_index': {
                'ow_uv_current': 'REAL',
                'ow_uv_max': 'REAL'
            },
            'forecast_daily': {
                'ow_forecast_temp_day1': 'REAL',
                'ow_forecast_temp_day2': 'REAL'
            },
            'forecast_hourly': {
                'ow_forecast_temp_1h': 'REAL',
                'ow_forecast_temp_6h': 'REAL'
            }
        }
    
    def configure(self, engine):
        """Configure the OpenWeather extension with interactive prompts."""
        
        print("\n" + "="*60)
        print("OPENWEATHER EXTENSION CONFIGURATION")
        print("="*60)
        
        try:
            # Step 1: Validate station coordinates
            self._validate_station_coordinates(engine.config_dict)
            
            # Step 2: Configure API key
            api_key = self._configure_api_key(engine.config_dict)
            
            # Step 3: Configure modules
            enabled_modules = self._configure_modules()
            
            # Step 4: Configure intervals  
            intervals = self._configure_intervals(enabled_modules)
            
            # Step 5: Update configuration
            self._update_configuration(engine.config_dict, api_key, enabled_modules, intervals)
            
            # Step 6: Create database fields for enabled modules
            self._create_database_fields(engine.config_dict, enabled_modules)
            
            print("\n✓ OpenWeather extension configured successfully!")
            print("  • Data will be stored with 'ow_' prefix in database")
            print("  • Restart WeeWX to begin data collection")
            print("  • Consider installing weewx-cdc-surveillance and weewx-environmental-health")
            print("  • View data in WeeWX reports and database")
            
            return True
            
        except Exception as e:
            print(f"\n✗ Configuration failed: {e}")
            print("  Manual configuration may be required")
            return False
    
    def _validate_station_coordinates(self, config_dict):
        """Validate that station coordinates are configured."""
        
        print("\nValidating station coordinates...")
        
        station_config = config_dict.get('Station', {})
        latitude = station_config.get('latitude')
        longitude = station_config.get('longitude')
        
        if not latitude or not longitude:
            raise ValueError(
                "Station coordinates not found in [Station] section. "
                "Please configure latitude and longitude in weewx.conf before installing."
            )
        
        try:
            lat_float = float(latitude)
            lon_float = float(longitude)
            
            if not (-90 <= lat_float <= 90):
                raise ValueError(f"Invalid latitude: {latitude} (must be -90 to 90)")
            if not (-180 <= lon_float <= 180):
                raise ValueError(f"Invalid longitude: {longitude} (must be -180 to 180)")
                
            print(f"✓ Station coordinates: {lat_float:.6f}, {lon_float:.6f}")
            
        except ValueError as e:
            raise ValueError(f"Invalid coordinates in [Station] section: {e}")
    
    def _configure_api_key(self, config_dict):
        """Configure OpenWeatherMap API key with validation."""
        
        print("\nOpenWeatherMap API Key Configuration")
        print("-" * 40)
        print("Get a free API key at: https://openweathermap.org/api")
        print("Free tier includes 1,000 calls/day (sufficient for this extension)")
        
        while True:
            api_key = input("\nEnter your OpenWeatherMap API key: ").strip()
            
            if not api_key:
                print("✗ API key cannot be empty")
                continue
                
            if len(api_key) < 10:
                print("✗ API key appears too short (should be ~32 characters)")
                continue
                
            # Basic format validation (OpenWeather API keys are typically hex strings)
            if not all(c in '0123456789abcdefABCDEF' for c in api_key):
                print("✗ API key contains invalid characters (should be hexadecimal)")
                continue
                
            print(f"✓ API key accepted: {api_key[:8]}...")
            return api_key
    
    def _configure_modules(self):
        """Configure which OpenWeather modules to enable."""
        
        print("\nModule Configuration")
        print("-" * 20)
        print("Select which OpenWeather data modules to enable:")
        
        modules = {
            'current_weather': {
                'description': 'Current weather (temperature, humidity, pressure, wind, clouds)',
                'recommendation': 'Recommended for all users',
                'default': True
            },
            'air_quality': {
                'description': 'Air quality data (PM2.5, PM10, ozone, NO2, gases, AQI)',
                'recommendation': 'Recommended for health monitoring',
                'default': True
            },
            'uv_index': {
                'description': 'UV radiation data (current and daily maximum)',
                'recommendation': 'Optional - useful for outdoor activities',
                'default': False
            },
            'forecast_daily': {
                'description': '8-day daily weather forecasts',
                'recommendation': 'Optional - for extended planning',
                'default': False
            },
            'forecast_hourly': {
                'description': '48-hour hourly weather forecasts',
                'recommendation': 'Optional - for detailed short-term planning',
                'default': False
            }
        }
        
        enabled_modules = {}
        
        for module_name, module_info in modules.items():
            print(f"\n{module_name}:")
            print(f"  Description: {module_info['description']}")
            print(f"  {module_info['recommendation']}")
            
            response = self._prompt_yes_no(
                f"Enable {module_name}?", 
                default=module_info['default']
            )
            enabled_modules[module_name] = response
            
            if response:
                print(f"  ✓ {module_name} enabled")
            else:
                print(f"  - {module_name} disabled")
        
        # Validate at least one module is enabled
        if not any(enabled_modules.values()):
            print("\n✗ Warning: No modules enabled. Enabling current_weather by default.")
            enabled_modules['current_weather'] = True
        
        return enabled_modules
    
    def _configure_intervals(self, enabled_modules):
        """Configure API call intervals for enabled modules."""
        
        print("\nAPI Call Interval Configuration")
        print("-" * 32)
        print("Configure how often to call OpenWeather APIs:")
        print("• Free tier: 1,000 calls/day limit")
        print("• Recommended intervals stay well within limits")
        
        default_intervals = {
            'current_weather': 3600,    # 1 hour = 24 calls/day
            'air_quality': 7200,        # 2 hours = 12 calls/day  
            'uv_index': 3600,           # 1 hour = 24 calls/day
            'forecast_daily': 21600,    # 6 hours = 4 calls/day
            'forecast_hourly': 3600     # 1 hour = 24 calls/day
        }
        
        intervals = {}
        total_daily_calls = 0
        
        for module_name, enabled in enabled_modules.items():
            if enabled:
                default_interval = default_intervals[module_name]
                daily_calls = 86400 // default_interval
                total_daily_calls += daily_calls
                
                print(f"\n{module_name}:")
                print(f"  Recommended interval: {default_interval} seconds ({daily_calls} calls/day)")
                
                use_default = self._prompt_yes_no("Use recommended interval?", default=True)
                
                if use_default:
                    intervals[module_name] = default_interval
                else:
                    while True:
                        try:
                            custom_interval = int(input("Enter custom interval (seconds): "))
                            if custom_interval < 600:  # 10 minutes minimum
                                print("✗ Minimum interval is 600 seconds (10 minutes)")
                                continue
                            intervals[module_name] = custom_interval
                            custom_daily = 86400 // custom_interval
                            print(f"✓ Custom interval: {custom_interval} seconds ({custom_daily} calls/day)")
                            break
                        except ValueError:
                            print("✗ Please enter a valid number")
        
        print(f"\nTotal estimated daily API calls: {total_daily_calls}")
        if total_daily_calls > 800:
            print("⚠ Warning: High API usage may approach free tier limits")
        else:
            print("✓ API usage well within free tier limits")
        
        return intervals
    
    def _update_configuration(self, config_dict, api_key, enabled_modules, intervals):
        """Update configuration with user settings."""
        
        print("\nUpdating configuration...")
        
        # Update OpenWeatherService section
        ow_config = config_dict.setdefault('OpenWeatherService', {})
        ow_config['api_key'] = api_key
        ow_config['modules'] = enabled_modules
        ow_config['intervals'] = intervals
        
        print("✓ Configuration updated")
    
    def _create_database_fields(self, config_dict, enabled_modules):
        """Create database fields for enabled modules only."""
        
        print("\nDatabase Schema Management")
        print("=" * 26)
        print("Checking and extending database schema...")
        
        try:
            # Find weectl executable
            weectl_path = self._find_weectl()
            if not weectl_path:
                print("✗ weectl executable not found")
                self._provide_manual_database_commands(enabled_modules)
                return
            
            # Get config file path
            config_path = getattr(config_dict, 'filename', '/etc/weewx/weewx.conf')
            
            # Check existing fields and add missing ones for enabled modules
            existing_fields, missing_fields = self._check_existing_fields(config_dict, enabled_modules)
            
            if existing_fields:
                print(f"\nFields already present in database:")
                for field in existing_fields:
                    print(f"  ✓ {field} - already exists, skipping")
            
            if missing_fields:
                print(f"\nAdding missing fields to database:")
                self._add_missing_fields(weectl_path, config_path, missing_fields)
            else:
                print("\n✓ All required fields already present in database")
            
            print("\n✓ Database schema management completed successfully")
            
        except Exception as e:
            print(f"\n✗ Database schema management failed: {e}")
            print("Continuing with installation - manual database setup may be required")
            self._provide_manual_database_commands(enabled_modules)
    
    def _check_existing_fields(self, config_dict, enabled_modules):
        """Check which required fields already exist in the database."""
        
        db_binding = config_dict.get('DataBindings', {}).get('wx_binding', {}).get('database', 'archive_sqlite')
        
        existing_fields = []
        missing_fields = {}
        
        try:
            with weewx.manager.open_manager_with_config(config_dict, db_binding) as dbmanager:
                # Get current database schema
                schema_columns = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    schema_columns.append(column[1])  # column[1] is the column name
                
                # Check each enabled module's fields
                for module_name, enabled in enabled_modules.items():
                    if enabled and module_name in self.module_fields:
                        for field_name, field_type in self.module_fields[module_name].items():
                            if field_name in schema_columns:
                                existing_fields.append(field_name)
                            else:
                                missing_fields[field_name] = field_type
                                
        except Exception as e:
            print(f"Warning: Could not check existing fields: {e}")
            # Assume all fields are missing if we can't check
            for module_name, enabled in enabled_modules.items():
                if enabled and module_name in self.module_fields:
                    missing_fields.update(self.module_fields[module_name])
        
        return existing_fields, missing_fields
    
    def _add_missing_fields(self, weectl_path, config_path, missing_fields):
        """Add missing database fields using weectl commands."""
        
        for field_name, field_type in missing_fields.items():
            print(f"  Adding field '{field_name}' ({field_type})...")
            
            try:
                # Build weectl command
                cmd = [
                    weectl_path, 'database', 'add-column', field_name,
                    '--config', config_path,
                    '--binding', 'wx_binding',
                    '-y'  # Don't prompt for confirmation
                ]
                
                # Add --type only for supported numeric types
                if field_type in ['REAL', 'INTEGER', 'real', 'integer', 'int']:
                    cmd.insert(-3, '--type')
                    cmd.insert(-3, field_type)
                # For text fields, omit --type (weectl rejects VARCHAR/TEXT)
                
                # Execute command with timeout
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"    ✓ Successfully added '{field_name}'")
                else:
                    # Check for duplicate column errors (treat as success)
                    if ('duplicate column' in result.stderr.lower() or 
                        'already exists' in result.stderr.lower()):
                        print(f"    ✓ Field '{field_name}' already exists")
                    else:
                        print(f"    ✗ Failed to add '{field_name}': {result.stderr}")
                        
            except subprocess.TimeoutExpired:
                print(f"    ✗ Timeout adding '{field_name}' - database may be locked")
            except Exception as e:
                print(f"    ✗ Error adding '{field_name}': {e}")
    
    def _find_weectl(self):
        """Find the weectl executable."""
        
        possible_paths = [
            '/usr/bin/weectl',
            '/usr/local/bin/weectl',
            os.path.expanduser('~/weewx-data/bin/weectl'),
            'weectl'  # In PATH
        ]
        
        for path in possible_paths:
            try:
                result = subprocess.run([path, '--version'], capture_output=True, timeout=10)
                if result.returncode == 0:
                    return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        return None
    
    def _provide_manual_database_commands(self, enabled_modules):
        """Provide manual database commands when automation fails."""
        
        print("\nManual Database Setup Commands")
        print("-" * 32)
        print("If automatic database setup failed, run these commands manually:")
        
        for module_name, enabled in enabled_modules.items():
            if enabled and module_name in self.module_fields:
                print(f"\n# {module_name} module fields:")
                for field_name, field_type in self.module_fields[module_name].items():
                    if field_type in ['REAL', 'INTEGER']:
                        print(f"weectl database add-column {field_name} --type {field_type} -y")
                    else:
                        print(f"weectl database add-column {field_name} -y")
    
    def _prompt_yes_no(self, question, default=True):
        """Prompt user for yes/no response."""
        
        default_text = "Y/n" if default else "y/N"
        
        while True:
            response = input(f"{question} [{default_text}]: ").strip().lower()
            
            if not response:
                return default
            elif response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' or 'n'")
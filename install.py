#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension Installer - Fixed with Field Selection

Provides interactive installation with field selection and dynamic database schema management.
Fixed using patterns from working AirVisual extension.

Copyright (C) 2025 WeeWX OpenWeather API Extension
"""

import sys
import os
import re
import yaml
import subprocess
import time
import configobj
from typing import Dict, List, Optional, Any

try:
    from weecfg.extension import ExtensionInstaller
    import weewx.manager
except ImportError:
    print("Error: This installer requires WeeWX 5.1 or later")
    sys.exit(1)

def loader():
    return OpenWeatherInstaller()


class TerminalUI:
    """Simple terminal UI for field selection."""
    
    def __init__(self):
        self.selected_items = set()
    
    def show_complexity_menu(self):
        """Show complexity level selection menu with field descriptions."""
        print("\n" + "="*80)
        print("OPENWEATHER DATA COLLECTION LEVEL")
        print("="*80)
        
        # Load defaults to show field lists
        try:
            defaults_path = os.path.join(os.path.dirname(__file__), 'field_selection_defaults.yaml')
            with open(defaults_path, 'r') as f:
                defaults = yaml.safe_load(f)['field_selection_defaults']
        except:
            # Fallback if YAML not available
            defaults = {
                'minimal': {'field_list': 'Temperature, humidity, pressure, wind speed, PM2.5, AQI'},
                'standard': {'field_list': 'Temperature, feels-like, humidity, pressure, wind speed & direction, cloud cover, PM2.5, AQI'},
                'comprehensive': {'field_list': 'All standard fields plus: visibility, wind gusts, daily min/max temp, PM10, ozone, NO2'},
                'everything': {'field_list': 'All 20+ fields including rain/snow data, atmospheric details, weather descriptions, and all air quality gases'}
            }
        
        options = [
            ("Minimal", defaults.get('minimal', {}).get('field_list', '4 essential fields')),
            ("Standard", defaults.get('standard', {}).get('field_list', '8 most common fields')),
            ("Comprehensive", defaults.get('comprehensive', {}).get('field_list', '15 advanced fields')),
            ("Everything", defaults.get('everything', {}).get('field_list', 'All available fields')),
            ("Custom", "Choose specific fields manually")
        ]
        
        print("\nChoose data collection level:")
        print("-" * 40)
        
        for i, (name, description) in enumerate(options, 1):
            print(f"{i}. {name}")
            print(f"   Fields: {description}")
            print()
        
        while True:
            try:
                choice = input("Enter choice [1-5]: ").strip()
                if choice in ['1', '2', '3', '4', '5']:
                    complexity_levels = ['minimal', 'standard', 'comprehensive', 'everything', 'custom']
                    selected = complexity_levels[int(choice) - 1]
                    print(f"\n✓ Selected: {options[int(choice) - 1][0]}")
                    return selected
                else:
                    print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
    
    def show_custom_selection(self, field_definitions):
        """Show interactive field selection (simplified for now)."""
        print("\n=== CUSTOM FIELD SELECTION ===")
        print("For this release, custom selection uses simplified interface.")
        print("You can enable/disable field categories:")
        
        selected_fields = {'current_weather': [], 'air_quality': []}
        
        # Simplified category-based selection
        for module_name, module_data in field_definitions.items():
            print(f"\n{module_name.upper().replace('_', ' ')} MODULE:")
            
            for category_name, category_data in module_data['categories'].items():
                while True:
                    try:
                        choice = input(f"  Enable {category_data['display_name']} fields? [y/n]: ").strip().lower()
                    except (KeyboardInterrupt, EOFError):
                        print("\nInstallation cancelled by user.")
                        sys.exit(1)
                    
                    if choice in ['y', 'yes']:
                        # Add all fields in this category
                        for field_name in category_data['fields'].keys():
                            selected_fields[module_name].append(field_name)
                        print(f"    ✓ {category_data['display_name']} enabled")
                        break
                    elif choice in ['n', 'no']:
                        print(f"    ○ {category_data['display_name']} disabled")
                        break
                    else:
                        print("    Please enter 'y' for yes or 'n' for no")
        
        return selected_fields
    
    def confirm_selection(self, complexity_level, field_count_estimate):
        """Confirm the user's selection before proceeding."""
        print(f"\n" + "="*60)
        print("CONFIGURATION CONFIRMATION")
        print("="*60)
        print(f"Data collection level: {complexity_level.title()}")
        print(f"Estimated database fields: {field_count_estimate}")
        print(f"This will modify your WeeWX database schema.")
        print("-" * 60)
        
        while True:
            try:
                confirm = input("Proceed with this configuration? [y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if confirm in ['y', 'yes']:
                return True
            elif confirm in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no")


class FieldSelectionHelper:
    """Helper class for field selection during installation."""
    
    def __init__(self, extension_dir):
        self.extension_dir = extension_dir
        self.defaults = self._load_defaults()
        self.field_definitions = self._load_field_definitions()
    
    def _load_defaults(self):
        """Load field selection defaults."""
        try:
            defaults_path = os.path.join(self.extension_dir, 'field_selection_defaults.yaml')
            with open(defaults_path, 'r') as f:
                return yaml.safe_load(f)['field_selection_defaults']
        except Exception as e:
            print(f"Warning: Could not load field defaults: {e}")
            return self._get_fallback_defaults()
    
    def _load_field_definitions(self):
        """Load field definitions."""
        try:
            definitions_path = os.path.join(self.extension_dir, 'openweather_fields.yaml')
            with open(definitions_path, 'r') as f:
                return yaml.safe_load(f)['field_definitions']
        except Exception as e:
            print(f"Warning: Could not load field definitions: {e}")
            return {'current_weather': {'categories': {}}, 'air_quality': {'categories': {}}}
    
    def _get_fallback_defaults(self):
        """Fallback defaults if YAML file not available."""
        return {
            'minimal': {
                'current_weather': ['temp', 'humidity', 'pressure', 'wind_speed'],
                'air_quality': ['pm2_5', 'aqi']
            },
            'standard': {
                'current_weather': ['temp', 'feels_like', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'cloud_cover'],
                'air_quality': ['pm2_5', 'aqi']
            },
            'comprehensive': {
                'current_weather': ['temp', 'feels_like', 'temp_min', 'temp_max', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'wind_gust', 'cloud_cover', 'visibility'],
                'air_quality': ['pm2_5', 'pm10', 'ozone', 'no2', 'aqi']
            },
            'everything': {
                'current_weather': 'all',
                'air_quality': 'all'
            }
        }
    
    def get_selected_fields(self, complexity_level):
        """Get field selection for complexity level."""
        return self.defaults.get(complexity_level, self.defaults.get('standard', {}))
    
    def estimate_field_count(self, selected_fields):
        """Estimate number of database fields for selection."""
        if not selected_fields:
            return 0
        
        count = 0
        for module, fields in selected_fields.items():
            if fields == 'all':
                # Count all fields in module
                if module in self.field_definitions:
                    for category_data in self.field_definitions[module]['categories'].values():
                        count += len(category_data['fields'])
            else:
                count += len(fields)
        
        return count
    
    def get_database_field_mappings(self, selected_fields):
        """Get database field mappings for selected fields."""
        mappings = {}
        
        for module, fields in selected_fields.items():
            if module in self.field_definitions:
                for category_data in self.field_definitions[module]['categories'].values():
                    for field_name, field_info in category_data['fields'].items():
                        if fields == 'all' or field_name in fields:
                            mappings[field_info['database_field']] = field_info['database_type']
        
        return mappings


class DatabaseManager:
    """Manages database schema creation during installation - FIXED VERSION."""
    
    def __init__(self, config_dict):
        self.config_dict = config_dict
    
    def create_database_fields(self, field_mappings):
        """Create database fields for selected data."""
        if not field_mappings:
            return 0
        
        print("\n" + "="*60)
        print("DATABASE SCHEMA MANAGEMENT")
        print("="*60)
        print("Checking and extending database schema...")
        print()
        
        # Check existing fields
        existing_fields = self._check_existing_fields()
        
        # Determine missing fields
        missing_fields = set(field_mappings.keys()) - set(existing_fields)
        already_present = set(field_mappings.keys()) & set(existing_fields)
        
        # Report existing fields
        if already_present:
            print("Fields already present in database:")
            for field in sorted(already_present):
                print(f"  ✓ {field} - already exists, skipping")
            print()
        
        # Add missing fields
        created_count = 0
        if missing_fields:
            print("Adding missing fields to database:")
            created_count = self._add_missing_fields(missing_fields, field_mappings)
        else:
            print("All required fields already exist in database.")
        
        print(f"\n✓ Database schema management completed successfully")
        print(f"  Fields already present: {len(already_present)}")
        print(f"  Fields created: {created_count}")
        
        return created_count
    
    def _check_existing_fields(self):
        """Check which OpenWeather fields already exist in database."""
        try:
            # FIXED: Use proper db_binding detection like AirVisual extension
            db_binding = self.config_dict.get('DataBindings', {}).get('wx_binding', 'wx_binding')
            
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                existing_fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    field_name = column[1]
                    if field_name.startswith('ow_'):  # Only OpenWeather fields
                        existing_fields.append(field_name)
            
            return existing_fields
        except Exception as e:
            print(f"  Warning: Could not check existing database fields: {e}")
            return []
    
    def _add_missing_fields(self, missing_fields, field_mappings):
        """Add missing database fields using weectl commands - FIXED VERSION."""
        created_count = 0
        
        # FIXED: Use AirVisual extension pattern for config_path
        config_path = getattr(self.config_dict, 'filename', '/etc/weewx/weewx.conf')
        
        # FIXED: Use AirVisual extension pattern for db_binding
        db_binding = self.config_dict.get('DataBindings', {}).get('wx_binding', 'wx_binding')
        
        # Find weectl executable
        weectl_path = self._find_weectl()
        if not weectl_path:
            print("  Error: weectl executable not found")
            self._print_manual_commands(missing_fields, field_mappings)
            return 0
        
        for field_name in sorted(missing_fields):
            field_type = field_mappings[field_name]
            
            try:
                print(f"  Adding field '{field_name}' ({field_type})...")
                
                # FIXED: Use complete command structure from AirVisual extension
                cmd = [
                    weectl_path, 'database', 'add-column', field_name,
                    '--config', config_path,
                    '--binding', db_binding,
                    '-y'
                ]
                
                # Only add --type for REAL/INTEGER (weectl limitation)
                if field_type in ['REAL', 'INTEGER']:
                    cmd.insert(-3, '--type')
                    cmd.insert(-3, field_type)
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"    ✓ Successfully added '{field_name}'")
                    created_count += 1
                elif 'duplicate column' in result.stderr.lower() or 'already exists' in result.stderr.lower():
                    print(f"    ✓ Field '{field_name}' already exists")
                    created_count += 1
                else:
                    print(f"    ✗ Failed to add '{field_name}': {result.stderr.strip()}")
                    
            except subprocess.TimeoutExpired:
                print(f"    ✗ Timeout adding '{field_name}'")
            except Exception as e:
                print(f"    ✗ Error adding '{field_name}': {e}")
        
        return created_count
    
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
                result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    return path
            except:
                continue
        
        return None
    
    def _print_manual_commands(self, missing_fields, field_mappings):
        """Print manual commands for database field creation."""
        print("\n  Manual database field creation commands:")
        print("  " + "-" * 50)
        
        for field_name in sorted(missing_fields):
            field_type = field_mappings[field_name]
            if field_type in ['REAL', 'INTEGER']:
                print(f"  weectl database add-column {field_name} --type {field_type} -y")
            else:
                print(f"  weectl database add-column {field_name} -y")
        
        print("  " + "-" * 50)


class OpenWeatherInstaller(ExtensionInstaller):
    """Enhanced installer with interactive field selection - FIXED VERSION."""
    
    def __init__(self):
        super(OpenWeatherInstaller, self).__init__(
            version="1.0.0",
            name="OpenWeather",
            description="OpenWeatherMap API integration with modular field selection",
            author="WeeWX OpenWeather Extension",
            author_email="",
            files=[
                ('bin/user', ['bin/user/openweather.py']),
                ('', ['field_selection_defaults.yaml', 'openweather_fields.yaml'])
            ],
            config={
                'OpenWeatherService': {
                    'enable': True,
                    'api_key': 'REPLACE_WITH_YOUR_API_KEY',
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
                        'complexity_level': 'standard'
                    }
                },
                'Engine': {
                    'Services': {
                        'data_services': 'user.openweather.OpenWeatherService'
                    }
                }
            }
        )
    
    def configure(self, engine):
        """Enhanced installation with interactive field selection - FIXED VERSION."""
        
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION INSTALLATION")
        print("="*80)
        print("This extension collects weather and air quality data from OpenWeatherMap.")
        print("You'll be guided through API setup and field selection.")
        print("-" * 80)
        
        try:
            # Step 1: API key setup
            api_key = self._prompt_api_key()
            
            # Step 2: Module selection
            modules = self._select_modules()
            
            # Step 3: Field selection
            extension_dir = os.path.dirname(__file__)
            field_helper = FieldSelectionHelper(extension_dir)
            
            ui = TerminalUI()
            complexity = ui.show_complexity_menu()
            
            if complexity == 'custom':
                # Custom field selection
                field_definitions = field_helper.field_definitions
                selected_fields = ui.show_custom_selection(field_definitions)
                if selected_fields is None or not any(selected_fields.values()):
                    # User selected no fields, fall back to standard
                    complexity = 'standard'
                    selected_fields = field_helper.get_selected_fields('standard')
            else:
                # Use smart defaults
                selected_fields = field_helper.get_selected_fields(complexity)
            
            # Step 4: Confirmation
            field_count = field_helper.estimate_field_count(selected_fields)
            if not ui.confirm_selection(complexity, field_count):
                print("\nInstallation cancelled by user.")
                return False
            
            # Step 5: Database schema creation
            field_mappings = field_helper.get_database_field_mappings(selected_fields)
            db_manager = DatabaseManager(engine.config_dict)
            created_count = db_manager.create_database_fields(field_mappings)
            
            # Step 6: Write configuration - FIXED VERSION
            self._write_configuration(engine, api_key, modules, complexity, selected_fields)
            
            # Step 7: Setup unit system
            self._setup_unit_system()
            
            print("\n" + "="*80)
            print("INSTALLATION COMPLETED SUCCESSFULLY!")
            print("="*80)
            print(f"✓ API key configured")
            print(f"✓ Data collection level: {complexity.title()}")
            print(f"✓ Database fields created: {created_count}")
            print(f"✓ Service registered: user.openweather.OpenWeatherService")
            print(f"✓ Unit system configured")
            print("-" * 80)
            print("Next steps:")
            print("1. Restart WeeWX: sudo systemctl restart weewx")
            print("2. Check logs: sudo journalctl -u weewx -f")
            print("3. Verify data collection in database/reports")
            print()
            print("For additional extensions, consider:")
            print("- weewx-cdc-surveillance (public health data)")
            print("- weewx-environmental-health (health risk assessment)")
            print("="*80)
            
            return True
            
        except Exception as e:
            print(f"\nInstallation failed: {e}")
            return False
    
    def _prompt_api_key(self):
        """Prompt for OpenWeatherMap API key with validation."""
        print("\n" + "="*60)
        print("OPENWEATHERMAP API KEY SETUP")
        print("="*60)
        print("You need a free API key from OpenWeatherMap.")
        print("1. Visit: https://openweathermap.org/api")
        print("2. Sign up for free account")
        print("3. Get your API key from the dashboard")
        print("-" * 60)
        
        while True:
            try:
                api_key = input("Enter your OpenWeatherMap API key: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if not api_key:
                print("API key cannot be empty. Please enter your API key.")
                continue
            
            if len(api_key) < 10:
                print("API key seems too short. Please verify and try again.")
                continue
            
            # Basic format validation
            if not re.match(r'^[a-fA-F0-9]+$', api_key):
                print("API key should contain only hexadecimal characters. Please verify and try again.")
                continue
            
            print(f"✓ API key accepted: {api_key[:8]}...")
            return api_key
    
    def _select_modules(self):
        """Select which OpenWeather modules to enable."""
        print("\n" + "="*60)
        print("MODULE SELECTION")
        print("="*60)
        print("Choose which OpenWeather data modules to enable:")
        print("-" * 60)
        
        modules = {}
        
        # Current weather (always recommended)
        while True:
            try:
                choice = input("Enable current weather data (temperature, humidity, pressure, wind)? [Y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if choice in ['', 'y', 'yes']:
                modules['current_weather'] = True
                print("✓ Current weather module enabled")
                break
            elif choice in ['n', 'no']:
                modules['current_weather'] = False
                print("○ Current weather module disabled")
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or press Enter for yes")
        
        # Air quality
        while True:
            try:
                choice = input("Enable air quality data (PM2.5, ozone, AQI)? [Y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if choice in ['', 'y', 'yes']:
                modules['air_quality'] = True
                print("✓ Air quality module enabled")
                break
            elif choice in ['n', 'no']:
                modules['air_quality'] = False
                print("○ Air quality module disabled")
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or press Enter for yes")
        
        return modules
    
    def _write_configuration(self, engine, api_key, modules, complexity, selected_fields):
        """Write configuration to weewx.conf - FIXED VERSION using AirVisual pattern."""
        
        # FIXED: Use simple direct dictionary assignment like AirVisual extension
        config_dict = engine.config_dict
        
        # Create OpenWeatherService configuration - SIMPLE APPROACH
        config_dict['OpenWeatherService'] = {
            'enable': True,
            'api_key': api_key,
            'timeout': 30,
            'log_success': False,
            'log_errors': True,
            'modules': modules,
            'intervals': {
                'current_weather': 3600,
                'air_quality': 7200
            },
            'field_selection': {
                'complexity_level': complexity,
                'selected_fields': selected_fields  # Simple storage
            }
        }
        
        # Register service using AirVisual pattern
        if 'Engine' not in config_dict:
            config_dict['Engine'] = {}
        if 'Services' not in config_dict['Engine']:
            config_dict['Engine']['Services'] = {}
        
        # Get current data_services list
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
            
            # Update configuration
            services['data_services'] = ', '.join(data_services_list)
    
    def _setup_unit_system(self):
        """Setup unit system extensions for OpenWeather data."""
        import weewx.units
        
        # Add concentration unit group for air quality
        if 'group_concentration' not in weewx.units.USUnits:
            weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
            weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
            weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
        
        # Add formatting for concentration
        if 'microgram_per_meter_cubed' not in weewx.units.default_unit_format_dict:
            weewx.units.default_unit_format_dict['microgram_per_meter_cubed'] = '%.1f'
        
        # Add label for concentration
        if 'microgram_per_meter_cubed' not in weewx.units.default_unit_label_dict:
            weewx.units.default_unit_label_dict['microgram_per_meter_cubed'] = ' μg/m³'


if __name__ == '__main__':
    print("This is a WeeWX extension installer.")
    print("Use: weectl extension install weewx-openweather.zip")
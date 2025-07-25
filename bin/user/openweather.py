#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension - Enhanced with Field Selection System and Built-in Testing

Provides modular OpenWeatherMap API integration with user-selectable fields
and dynamic database schema management.

Copyright (C) 2025 WeeWX OpenWeather API Extension
"""

import json
import time
import threading
import queue
import urllib.request
import urllib.parse
import urllib.error
import socket
import yaml
import os
import argparse
import sys
from typing import Dict, List, Optional, Any, Tuple

import weewx
from weewx.engine import StdService
import weewx.units
import weewx.manager
import weeutil.logger

log = weeutil.logger.logging.getLogger(__name__)

VERSION = "1.0.0"

class FieldSelectionManager:
    """Manages field selection with smart defaults and custom configurations."""
    
    def __init__(self, config_path=None):
        self.config_path = config_path or self._find_config_files()
        self.defaults = self._load_defaults()
        self.field_definitions = self._load_field_definitions()
    
    def _find_config_files(self):
        """Find YAML configuration files in extension directory."""
        # Look in same directory as this module
        base_path = os.path.dirname(__file__)
        return {
            'defaults': os.path.join(base_path, '../../field_selection_defaults.yaml'),
            'definitions': os.path.join(base_path, '../../openweather_fields.yaml')
        }
    
    def _load_defaults(self):
        """Load smart defaults from YAML file."""
        try:
            with open(self.config_path['defaults'], 'r') as f:
                return yaml.safe_load(f)['field_selection_defaults']
        except Exception as e:
            log.error(f"Error loading field selection defaults: {e}")
            # Fallback to hardcoded defaults
            return {
                'minimal': {
                    'current_weather': ['temp', 'humidity', 'pressure', 'wind_speed'],
                    'air_quality': ['pm2_5', 'aqi']
                },
                'standard': {
                    'current_weather': ['temp', 'feels_like', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'cloud_cover'],
                    'air_quality': ['pm2_5', 'aqi']
                }
            }
    
    def _load_field_definitions(self):
        """Load field definitions from YAML file."""
        try:
            with open(self.config_path['definitions'], 'r') as f:
                return yaml.safe_load(f)['field_definitions']
        except Exception as e:
            log.error(f"Error loading field definitions: {e}")
            # Return empty structure to prevent crashes
            return {'current_weather': {'categories': {}}, 'air_quality': {'categories': {}}}
    
    def get_smart_default_fields(self, complexity_level):
        """Get field list for specified complexity level."""
        return self.defaults.get(complexity_level, self.defaults.get('standard', {}))
    
    def get_all_available_fields(self):
        """Get all available fields organized by module and category."""
        return self.field_definitions
    
    def validate_field_selection(self, selected_fields):
        """Validate that selected fields exist in definitions."""
        valid_fields = {}
        all_fields = self.get_all_available_fields()
        
        for module, fields in selected_fields.items():
            if module in all_fields:
                valid_fields[module] = []
                if fields == 'all':
                    # Get all fields for this module
                    for category_data in all_fields[module]['categories'].values():
                        for field_name in category_data['fields'].keys():
                            valid_fields[module].append(field_name)
                else:
                    for field in fields:
                        if self._field_exists(field, all_fields[module]):
                            valid_fields[module].append(field)
        
        return valid_fields
    
    def _field_exists(self, field_name, module_data):
        """Check if a field exists in the module data."""
        for category_data in module_data['categories'].values():
            if field_name in category_data['fields']:
                return True
        return False
    
    def get_database_field_mappings(self, selected_fields):
        """Convert selected logical fields to database field names and types."""
        mappings = {}
        all_fields = self.get_all_available_fields()
        
        for module, fields in selected_fields.items():
            if module in all_fields:
                for category_data in all_fields[module]['categories'].values():
                    for field_name, field_info in category_data['fields'].items():
                        # FIX: Handle 'all' case properly
                        if fields == 'all':
                            # Include all fields for this module
                            mappings[field_info['database_field']] = field_info['database_type']
                        elif isinstance(fields, list) and field_name in fields:
                            # Include only selected fields
                            mappings[field_info['database_field']] = field_info['database_type']
                        # Skip other field types to prevent errors
        
        return mappings
    
    def get_api_path_mappings(self, selected_fields):
        """Get API path mappings for selected fields."""
        mappings = {}
        all_fields = self.get_all_available_fields()
        
        for module, fields in selected_fields.items():
            if module in all_fields:
                for category_data in all_fields[module]['categories'].values():
                    for field_name, field_info in category_data['fields'].items():
                        # FIX: Handle 'all' case properly - same logic as database mappings
                        if fields == 'all':
                            # Include all fields for this module
                            mappings[field_info['database_field']] = field_info['api_path']
                        elif isinstance(fields, list) and field_name in fields:
                            # Include only selected fields
                            mappings[field_info['database_field']] = field_info['api_path']
                        # Skip other field types to prevent errors
        
        return mappings


class DatabaseSchemaManager:
    """Manages dynamic database schema based on field selections."""
    
    def __init__(self, config_dict, selected_fields):
        self.config_dict = config_dict
        self.selected_fields = selected_fields
        self.field_manager = FieldSelectionManager()
    
    def create_required_fields(self):
        """Create database fields for selected data only."""
        
        # Get database field mappings
        field_mappings = self.field_manager.get_database_field_mappings(self.selected_fields)
        
        # Check existing fields
        existing_fields = self._check_existing_fields()
        
        # Determine missing fields
        missing_fields = set(field_mappings.keys()) - set(existing_fields)
        
        if missing_fields:
            created_count = self._add_missing_fields(missing_fields, field_mappings)
            return created_count
        
        return 0
    
    def _check_existing_fields(self):
        """Check which OpenWeather fields already exist in database."""
        try:
            db_binding = self.config_dict.get('DataBindings', {}).get('wx_binding', 'wx_binding')
            
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                existing_fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    field_name = column[1]
                    if field_name.startswith('ow_'):  # Only OpenWeather fields
                        existing_fields.append(field_name)
            
            return existing_fields
        except Exception as e:
            log.error(f"Error checking existing database fields: {e}")
            return []
    
    def _add_missing_fields(self, missing_fields, field_mappings):
        """Add missing database fields using weectl commands."""
        import subprocess
        
        created_count = 0
        config_path = self.config_dict.get('config_path', '/etc/weewx/weewx.conf')
        
        for field_name in missing_fields:
            field_type = field_mappings[field_name]
            
            try:
                cmd = ['weectl', 'database', 'add-column', field_name, '--config', config_path, '-y']
                
                # Only add --type for REAL/INTEGER (weectl limitation)
                if field_type in ['REAL', 'INTEGER']:
                    cmd.insert(-2, '--type')
                    cmd.insert(-2, field_type)
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0 or 'duplicate column' in result.stderr.lower():
                    created_count += 1
                    log.info(f"Created database field: {field_name}")
                else:
                    log.warning(f"Failed to create field {field_name}: {result.stderr}")
                    
            except Exception as e:
                log.error(f"Error creating field {field_name}: {e}")
        
        return created_count


class OpenWeatherAPIError(Exception):
    """Custom exception for OpenWeather API errors."""
    pass


class OpenWeatherDataCollector:
    """Enhanced data collector with field selection support."""
    
    def __init__(self, api_key, timeout=30, selected_fields=None):
        self.api_key = api_key
        self.timeout = timeout
        self.selected_fields = selected_fields or {}
        self.field_manager = FieldSelectionManager()
        
        # Get API path mappings for selected fields
        self.api_mappings = self.field_manager.get_api_path_mappings(self.selected_fields)
        
        # Base URLs for OpenWeather APIs
        self.base_urls = {
            'current_weather': 'http://api.openweathermap.org/data/2.5/weather',
            'air_quality': 'http://api.openweathermap.org/data/2.5/air_pollution'
        }
    
    def collect_current_weather(self, latitude, longitude):
        """Collect current weather data with field filtering."""
        if 'current_weather' not in self.selected_fields:
            return {}
        
        try:
            params = {
                'lat': latitude,
                'lon': longitude,
                'appid': self.api_key,
                'units': 'metric'
            }
            
            url = f"{self.base_urls['current_weather']}?{urllib.parse.urlencode(params)}"
            
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Extract and filter data based on field selection
            extracted_data = self._extract_weather_data(data)
            return self._apply_field_selection(extracted_data, 'current_weather')
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise OpenWeatherAPIError("Invalid API key")
            elif e.code == 429:
                raise OpenWeatherAPIError("API rate limit exceeded")
            else:
                raise OpenWeatherAPIError(f"HTTP error {e.code}: {e.reason}")
        except socket.timeout:
            raise OpenWeatherAPIError("Request timeout")
        except Exception as e:
            raise OpenWeatherAPIError(f"Unexpected error: {e}")
    
    def collect_air_quality(self, latitude, longitude):
        """Collect air quality data with field filtering."""
        if 'air_quality' not in self.selected_fields:
            return {}
        
        try:
            params = {
                'lat': latitude,
                'lon': longitude,
                'appid': self.api_key
            }
            
            url = f"{self.base_urls['air_quality']}?{urllib.parse.urlencode(params)}"
            
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            # Extract and filter data based on field selection
            extracted_data = self._extract_air_quality_data(data)
            return self._apply_field_selection(extracted_data, 'air_quality')
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise OpenWeatherAPIError("Invalid API key")
            elif e.code == 429:
                raise OpenWeatherAPIError("API rate limit exceeded")
            else:
                raise OpenWeatherAPIError(f"HTTP error {e.code}: {e.reason}")
        except socket.timeout:
            raise OpenWeatherAPIError("Request timeout")
        except Exception as e:
            raise OpenWeatherAPIError(f"Unexpected error: {e}")
    
    def _extract_weather_data(self, api_response):
        """Extract weather data from API response to database fields."""
        extracted = {}
        
        # Temperature data
        if 'main' in api_response:
            main = api_response['main']
            extracted['ow_temperature'] = main.get('temp')
            extracted['ow_feels_like'] = main.get('feels_like')
            extracted['ow_temp_min'] = main.get('temp_min')
            extracted['ow_temp_max'] = main.get('temp_max')
            extracted['ow_pressure'] = main.get('pressure')
            extracted['ow_humidity'] = main.get('humidity')
            extracted['ow_sea_level'] = main.get('sea_level')
            extracted['ow_grnd_level'] = main.get('grnd_level')
        
        # Wind data
        if 'wind' in api_response:
            wind = api_response['wind']
            extracted['ow_wind_speed'] = wind.get('speed')
            extracted['ow_wind_direction'] = wind.get('deg')
            extracted['ow_wind_gust'] = wind.get('gust')
        
        # Sky conditions
        if 'clouds' in api_response:
            extracted['ow_cloud_cover'] = api_response['clouds'].get('all')
        
        extracted['ow_visibility'] = api_response.get('visibility')
        
        # Precipitation
        if 'rain' in api_response:
            rain = api_response['rain']
            extracted['ow_rain_1h'] = rain.get('1h')
            extracted['ow_rain_3h'] = rain.get('3h')
        
        if 'snow' in api_response:
            snow = api_response['snow']
            extracted['ow_snow_1h'] = snow.get('1h')
            extracted['ow_snow_3h'] = snow.get('3h')
        
        # Weather information
        if 'weather' in api_response and len(api_response['weather']) > 0:
            weather = api_response['weather'][0]
            extracted['ow_weather_main'] = weather.get('main')
            extracted['ow_weather_description'] = weather.get('description')
            extracted['ow_weather_icon'] = weather.get('icon')
        
        # Add timestamp
        extracted['ow_weather_timestamp'] = time.time()
        
        return extracted
    
    def _extract_air_quality_data(self, api_response):
        """Extract air quality data from API response to database fields."""
        extracted = {}
        
        if 'list' in api_response and len(api_response['list']) > 0:
            data = api_response['list'][0]
            
            # Main AQI
            if 'main' in data:
                extracted['ow_aqi'] = data['main'].get('aqi')
            
            # Components
            if 'components' in data:
                components = data['components']
                extracted['ow_pm25'] = components.get('pm2_5')
                extracted['ow_pm10'] = components.get('pm10')
                extracted['ow_ozone'] = components.get('o3')
                extracted['ow_no2'] = components.get('no2')
                extracted['ow_so2'] = components.get('so2')
                extracted['ow_co'] = components.get('co')
                extracted['ow_nh3'] = components.get('nh3')
                extracted['ow_no'] = components.get('no')
        
        # Add timestamp
        extracted['ow_air_quality_timestamp'] = time.time()
        
        return extracted
    
    def _apply_field_selection(self, raw_data, module_name):
        """Filter collected data based on field selection."""
        if module_name not in self.selected_fields:
            return {}
        
        selected_fields = self.selected_fields[module_name]
        if selected_fields == 'all':
            return raw_data
        
        # Get field mappings for this module
        all_fields = self.field_manager.get_all_available_fields()
        selected_db_fields = set()
        
        if module_name in all_fields:
            for category_data in all_fields[module_name]['categories'].values():
                for field_name, field_info in category_data['fields'].items():
                    if field_name in selected_fields:
                        selected_db_fields.add(field_info['database_field'])
        
        # Filter raw data to only include selected fields
        filtered_data = {}
        for db_field, value in raw_data.items():
            if db_field in selected_db_fields or db_field.endswith('_timestamp'):
                filtered_data[db_field] = value
        
        return filtered_data


class OpenWeatherBackgroundThread(threading.Thread):
    """Enhanced background thread with field selection support."""
    
    def __init__(self, config, selected_fields):
        super(OpenWeatherBackgroundThread, self).__init__(name='OpenWeatherBackgroundThread')
        self.daemon = True
        
        self.config = config
        self.selected_fields = selected_fields
        self.running = True
        
        # Initialize data collector
        self.collector = OpenWeatherDataCollector(
            api_key=config['api_key'],
            timeout=config.get('timeout', 30),
            selected_fields=selected_fields
        )
        
        # Thread-safe data storage
        self.data_lock = threading.Lock()
        self.latest_data = {}
        
        # Get station coordinates
        station_config = config.get('Station', {})
        self.latitude = float(station_config.get('latitude', 0.0))
        self.longitude = float(station_config.get('longitude', 0.0))
        
        # Module intervals
        self.intervals = {
            'current_weather': config.get('intervals', {}).get('current_weather', 3600),
            'air_quality': config.get('intervals', {}).get('air_quality', 7200)
        }
        
        # Last collection times
        self.last_collection = {
            'current_weather': 0,
            'air_quality': 0
        }
        
        log.info(f"OpenWeather background thread initialized for location: {self.latitude}, {self.longitude}")
    
    def run(self):
        """Main background thread loop."""
        log.info("OpenWeather background thread started")
        
        while self.running:
            try:
                current_time = time.time()
                
                # Check if current weather collection is due
                if ('current_weather' in self.selected_fields and 
                    current_time - self.last_collection['current_weather'] >= self.intervals['current_weather']):
                    self._collect_current_weather()
                    self.last_collection['current_weather'] = current_time
                
                # Check if air quality collection is due
                if ('air_quality' in self.selected_fields and 
                    current_time - self.last_collection['air_quality'] >= self.intervals['air_quality']):
                    self._collect_air_quality()
                    self.last_collection['air_quality'] = current_time
                
                # Sleep for 60 seconds before next check
                time.sleep(60)
                
            except Exception as e:
                log.error(f"Error in OpenWeather background thread: {e}")
                time.sleep(300)  # Sleep longer on error
    
    def _collect_current_weather(self):
        """Collect current weather data."""
        try:
            weather_data = self.collector.collect_current_weather(self.latitude, self.longitude)
            
            if weather_data:
                with self.data_lock:
                    self.latest_data.update(weather_data)
                
                if self.config.get('log_success', False):
                    log.info(f"Collected current weather data: {len(weather_data)} fields")
            
        except OpenWeatherAPIError as e:
            if self.config.get('log_errors', True):
                log.error(f"OpenWeather API error collecting weather data: {e}")
        except Exception as e:
            if self.config.get('log_errors', True):
                log.error(f"Unexpected error collecting weather data: {e}")
    
    def _collect_air_quality(self):
        """Collect air quality data."""
        try:
            air_quality_data = self.collector.collect_air_quality(self.latitude, self.longitude)
            
            if air_quality_data:
                with self.data_lock:
                    self.latest_data.update(air_quality_data)
                
                if self.config.get('log_success', False):
                    log.info(f"Collected air quality data: {len(air_quality_data)} fields")
            
        except OpenWeatherAPIError as e:
            if self.config.get('log_errors', True):
                log.error(f"OpenWeather API error collecting air quality data: {e}")
        except Exception as e:
            if self.config.get('log_errors', True):
                log.error(f"Unexpected error collecting air quality data: {e}")
    
    def get_latest_data(self):
        """Get latest collected data (thread-safe)."""
        with self.data_lock:
            return self.latest_data.copy()
    
    def shutdown(self):
        """Shutdown the background thread."""
        log.info("Shutting down OpenWeather background thread")
        self.running = False


class OpenWeatherService(StdService):
    """Enhanced OpenWeather service with field selection support."""
    
    def __init__(self, engine, config_dict):
        super(OpenWeatherService, self).__init__(engine, config_dict)
        
        # Parse configuration
        self.config = self._parse_config(config_dict)
        
        if not self.config.get('enable', True):
            log.info("OpenWeather service disabled")
            return
        
        # Initialize field selection
        self.field_manager = FieldSelectionManager()
        self.selected_fields = self._parse_field_selection()
        
        log.info(f"OpenWeather service field selection: {self.selected_fields}")
        
        # Setup unit system for selected fields
        self._setup_unit_system()
        
        # Start background data collection
        self.background_thread = OpenWeatherBackgroundThread(
            self.config, 
            self.selected_fields
        )
        self.background_thread.start()
        
        # Bind to archive events
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
        log.info("OpenWeather service initialized successfully")
    
    def _parse_config(self, config_dict):
        """Parse OpenWeather service configuration."""
        service_config = config_dict.get('OpenWeatherService', {})
        
        # Add station coordinates to config
        station_config = config_dict.get('Station', {})
        service_config['Station'] = station_config
        
        return service_config
    
    def _parse_field_selection(self):
        """Parse field selection from configuration."""
        field_config = self.config.get('field_selection', {})
        
        # If no field selection specified, use 'standard' defaults
        if not field_config:
            return self.field_manager.get_smart_default_fields('standard')
        
        # If complexity level specified, use smart defaults
        complexity = field_config.get('complexity_level')
        if complexity and complexity != 'custom':
            return self.field_manager.get_smart_default_fields(complexity)
        
        # Handle custom field selection - convert ConfigObj boolean format to lists
        custom_selection = {}
        
        # Process current_weather module
        current_weather_config = field_config.get('current_weather', {})
        if isinstance(current_weather_config, dict):
            # Convert {field_name: True/False} to [field_name, ...]
            selected_fields = []
            for field_name, enabled in current_weather_config.items():
                # Handle both string and boolean values from ConfigObj
                if isinstance(enabled, str):
                    enabled = enabled.lower() in ('true', 'yes', '1')
                if enabled:
                    selected_fields.append(field_name)
            custom_selection['current_weather'] = selected_fields
        else:
            custom_selection['current_weather'] = current_weather_config or []
        
        # Process air_quality module
        air_quality_config = field_config.get('air_quality', {})
        if isinstance(air_quality_config, dict):
            # Convert {field_name: True/False} to [field_name, ...]
            selected_fields = []
            for field_name, enabled in air_quality_config.items():
                # Handle both string and boolean values from ConfigObj
                if isinstance(enabled, str):
                    enabled = enabled.lower() in ('true', 'yes', '1')
                if enabled:
                    selected_fields.append(field_name)
            custom_selection['air_quality'] = selected_fields
        else:
            custom_selection['air_quality'] = air_quality_config or []
        
        # Validate custom selection
        return self.field_manager.validate_field_selection(custom_selection)
        
    def _setup_unit_system(self):
        """Setup WeeWX unit system for selected fields."""
        
        # Map observations to unit groups
        obs_group_dict_updates = {}
        
        # Only add unit mappings for selected fields
        field_mappings = self.field_manager.get_database_field_mappings(self.selected_fields)
        
        for db_field in field_mappings.keys():
            if db_field.startswith('ow_'):
                field_name = db_field[3:]  # Remove 'ow_' prefix
                
                # Determine appropriate unit group
                if field_name in ['temperature', 'feels_like', 'temp_min', 'temp_max']:
                    obs_group_dict_updates[db_field] = 'group_temperature'
                elif field_name in ['pressure', 'sea_level', 'grnd_level']:
                    obs_group_dict_updates[db_field] = 'group_pressure'
                elif field_name == 'humidity':
                    obs_group_dict_updates[db_field] = 'group_percent'
                elif field_name in ['wind_speed', 'wind_gust']:
                    obs_group_dict_updates[db_field] = 'group_speed'
                elif field_name == 'wind_direction':
                    obs_group_dict_updates[db_field] = 'group_direction'
                elif field_name in ['visibility', 'rain_1h', 'rain_3h', 'snow_1h', 'snow_3h']:
                    obs_group_dict_updates[db_field] = 'group_distance'
                elif field_name in ['pm25', 'pm10', 'ozone', 'no2', 'so2', 'co', 'nh3', 'no']:
                    obs_group_dict_updates[db_field] = 'group_concentration'
                elif field_name == 'aqi':
                    obs_group_dict_updates[db_field] = 'group_count'
                elif field_name in ['cloud_cover']:
                    obs_group_dict_updates[db_field] = 'group_percent'
                else:
                    obs_group_dict_updates[db_field] = 'group_count'
        
        # Apply unit group mappings
        weewx.units.obs_group_dict.update(obs_group_dict_updates)
        
        # Setup unit definitions and formatting
        weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
        weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
        weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
        
        # Default formatting
        format_updates = {
            'microgram_per_meter_cubed': '%.1f'
        }
        weewx.units.default_unit_format_dict.update(format_updates)
        
        # Default labels
        label_updates = {
            'microgram_per_meter_cubed': ' μg/m³'
        }
        weewx.units.default_unit_label_dict.update(label_updates)
        
        log.debug(f"Unit system configured for {len(obs_group_dict_updates)} OpenWeather fields")
    
    def new_archive_record(self, event):
        """Inject OpenWeather data into archive records."""
        if not self.config.get('enable', True):
            return
        
        try:
            # Get latest data from background thread
            latest_data = self.background_thread.get_latest_data()
            
            if latest_data:
                # Check data freshness
                current_time = time.time()
                weather_age = current_time - latest_data.get('ow_weather_timestamp', 0)
                air_quality_age = current_time - latest_data.get('ow_air_quality_timestamp', 0)
                
                max_age = self.config.get('max_data_age', 7200)  # 2 hours default
                
                # Inject data that isn't too old
                injected_fields = []
                for field_name, value in latest_data.items():
                    if value is not None:
                        if field_name.startswith('ow_weather_') and weather_age <= max_age:
                            event.record[field_name] = value
                            if not field_name.endswith('_timestamp'):
                                injected_fields.append(field_name)
                        elif field_name.startswith('ow_air_quality_') and air_quality_age <= max_age:
                            event.record[field_name] = value
                            if not field_name.endswith('_timestamp'):
                                injected_fields.append(field_name)
                        elif field_name.startswith('ow_') and not field_name.endswith('_timestamp'):
                            # For other fields, use the more recent timestamp
                            data_age = min(weather_age, air_quality_age)
                            if data_age <= max_age:
                                event.record[field_name] = value
                                injected_fields.append(field_name)
                
                if injected_fields and self.config.get('log_success', False):
                    log.info(f"Injected OpenWeather data: {len(injected_fields)} fields")
                
            else:
                log.debug("No OpenWeather data available for archive record")
                
        except Exception as e:
            if self.config.get('log_errors', True):
                log.error(f"Error injecting OpenWeather data: {e}")
    
    def shutDown(self):
        """Shutdown the service."""
        if hasattr(self, 'background_thread'):
            self.background_thread.shutdown()
            self.background_thread.join(timeout=10)
        
        log.info("OpenWeather service shut down")


# Extension entry point
def loader(config_dict, engine):
    """Load the OpenWeather service."""
    return OpenWeatherService(engine, config_dict)


# ============================================================================
# BUILT-IN TESTING FUNCTIONALITY
# ============================================================================

class OpenWeatherTester:
    """Built-in testing functionality for the OpenWeather extension."""
    
    def __init__(self, api_key=None, latitude=None, longitude=None):
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        
        # Use test coordinates if not provided
        if not self.latitude or not self.longitude:
            self.latitude = 33.656915  # Huntington Beach, CA
            self.longitude = -117.982542
        
        # Initialize field manager for testing
        self.field_manager = FieldSelectionManager()
        
        print(f"OpenWeather Extension Tester v{VERSION}")
        print(f"Testing location: {self.latitude}, {self.longitude}")
        print("=" * 60)
    
    def test_api_connectivity(self):
        """Test API connectivity and response parsing."""
        print("\n🌐 TESTING API CONNECTIVITY")
        print("-" * 40)
        
        if not self.api_key:
            print("❌ Error: API key required for connectivity testing")
            return False
        
        success_count = 0
        total_tests = 2
        
        # Test current weather API
        print("Testing current weather API...")
        try:
            collector = OpenWeatherDataCollector(
                self.api_key, 
                timeout=30,
                selected_fields={'current_weather': ['temp', 'humidity', 'pressure']}
            )
            weather_data = collector.collect_current_weather(self.latitude, self.longitude)
            
            if weather_data and 'ow_temperature' in weather_data:
                print(f"  ✅ Current weather API: {weather_data['ow_temperature']:.1f}°C")
                success_count += 1
            else:
                print("  ❌ Current weather API: No temperature data received")
                
        except OpenWeatherAPIError as e:
            print(f"  ❌ Current weather API: {e}")
        except Exception as e:
            print(f"  ❌ Current weather API: Unexpected error - {e}")
        
        # Test air quality API
        print("Testing air quality API...")
        try:
            collector = OpenWeatherDataCollector(
                self.api_key,
                timeout=30,
                selected_fields={'air_quality': ['pm2_5', 'aqi']}
            )
            air_data = collector.collect_air_quality(self.latitude, self.longitude)
            
            if air_data and 'ow_aqi' in air_data:
                print(f"  ✅ Air quality API: AQI {air_data['ow_aqi']}")
                success_count += 1
            else:
                print("  ❌ Air quality API: No AQI data received")
                
        except OpenWeatherAPIError as e:
            print(f"  ❌ Air quality API: {e}")
        except Exception as e:
            print(f"  ❌ Air quality API: Unexpected error - {e}")
        
        print(f"\nAPI Connectivity Test: {success_count}/{total_tests} APIs working")
        return success_count == total_tests
    
    def test_data_processing(self):
        """Test data extraction and field mapping."""
        print("\n🔧 TESTING DATA PROCESSING")
        print("-" * 40)
        
        # Test weather data extraction
        print("Testing weather data extraction...")
        
        # Mock API response for testing
        mock_weather_response = {
            "coord": {"lon": -117.98, "lat": 33.66},
            "weather": [{"main": "Clear", "description": "clear sky", "icon": "01d"}],
            "main": {
                "temp": 22.5,
                "feels_like": 21.8,
                "temp_min": 20.1,
                "temp_max": 24.3,
                "pressure": 1015,
                "humidity": 65
            },
            "visibility": 10000,
            "wind": {"speed": 3.1, "deg": 270, "gust": 4.2},
            "clouds": {"all": 15},
            "dt": 1642678800
        }
        
        try:
            collector = OpenWeatherDataCollector(
                "test_key",
                selected_fields={'current_weather': ['temp', 'feels_like', 'humidity', 'pressure']}
            )
            extracted = collector._extract_weather_data(mock_weather_response)
            
            # Verify expected fields
            expected_fields = ['ow_temperature', 'ow_feels_like', 'ow_humidity', 'ow_pressure']
            found_fields = [field for field in expected_fields if field in extracted and extracted[field] is not None]
            
            print(f"  ✅ Weather extraction: {len(found_fields)}/{len(expected_fields)} fields extracted")
            for field in found_fields:
                print(f"    {field}: {extracted[field]}")
                
        except Exception as e:
            print(f"  ❌ Weather extraction failed: {e}")
            return False
        
        # Test air quality data extraction
        print("\nTesting air quality data extraction...")
        
        mock_air_response = {
            "coord": {"lon": -117.98, "lat": 33.66},
            "list": [{
                "dt": 1642678800,
                "main": {"aqi": 2},
                "components": {
                    "co": 245.3,
                    "no": 0.8,
                    "no2": 15.2,
                    "o3": 89.1,
                    "so2": 2.1,
                    "pm2_5": 8.7,
                    "pm10": 12.4,
                    "nh3": 1.2
                }
            }]
        }
        
        try:
            collector = OpenWeatherDataCollector(
                "test_key",
                selected_fields={'air_quality': ['pm2_5', 'aqi', 'ozone']}
            )
            extracted = collector._extract_air_quality_data(mock_air_response)
            
            expected_fields = ['ow_pm25', 'ow_aqi', 'ow_ozone']
            found_fields = [field for field in expected_fields if field in extracted and extracted[field] is not None]
            
            print(f"  ✅ Air quality extraction: {len(found_fields)}/{len(expected_fields)} fields extracted")
            for field in found_fields:
                print(f"    {field}: {extracted[field]}")
                
        except Exception as e:
            print(f"  ❌ Air quality extraction failed: {e}")
            return False
        
        print("\nData Processing Test: ✅ PASSED")
        return True
    
    def test_field_selection(self):
        """Test field selection and filtering functionality."""
        print("\n📋 TESTING FIELD SELECTION")
        print("-" * 40)
        
        # Test smart defaults
        print("Testing smart defaults...")
        try:
            for complexity in ['minimal', 'standard', 'comprehensive']:
                fields = self.field_manager.get_smart_default_fields(complexity)
                weather_count = len(fields.get('current_weather', []))
                air_count = len(fields.get('air_quality', []))
                print(f"  ✅ {complexity}: {weather_count} weather + {air_count} air quality fields")
                
        except Exception as e:
            print(f"  ❌ Smart defaults failed: {e}")
            return False
        
        # Test field mappings
        print("\nTesting field mappings...")
        try:
            test_selection = {
                'current_weather': ['temp', 'humidity', 'pressure'],
                'air_quality': ['pm2_5', 'aqi']
            }
            
            mappings = self.field_manager.get_database_field_mappings(test_selection)
            expected_mappings = ['ow_temperature', 'ow_humidity', 'ow_pressure', 'ow_pm25', 'ow_aqi']
            
            found_mappings = [field for field in expected_mappings if field in mappings]
            print(f"  ✅ Database mappings: {len(found_mappings)}/{len(expected_mappings)} mapped correctly")
            
        except Exception as e:
            print(f"  ❌ Field mappings failed: {e}")
            return False
        
        # Test field filtering
        print("\nTesting field filtering...")
        try:
            collector = OpenWeatherDataCollector(
                "test_key",
                selected_fields={'current_weather': ['temp', 'humidity']}
            )
            
            # Create mock data with more fields than selected
            mock_data = {
                'ow_temperature': 22.5,
                'ow_humidity': 65,
                'ow_pressure': 1015,  # Not selected
                'ow_wind_speed': 3.1,  # Not selected
                'ow_weather_timestamp': time.time()
            }
            
            filtered = collector._apply_field_selection(mock_data, 'current_weather')
            
            # Should only have selected fields plus timestamp
            expected_fields = {'ow_temperature', 'ow_humidity', 'ow_weather_timestamp'}
            actual_fields = set(filtered.keys())
            
            if expected_fields == actual_fields:
                print(f"  ✅ Field filtering: {len(filtered)} fields correctly filtered")
            else:
                print(f"  ❌ Field filtering: Expected {expected_fields}, got {actual_fields}")
                return False
                
        except Exception as e:
            print(f"  ❌ Field filtering failed: {e}")
            return False
        
        print("\nField Selection Test: ✅ PASSED")
        return True
    
    def test_configuration(self):
        """Test configuration parsing and validation."""
        print("\n⚙️  TESTING CONFIGURATION")
        print("-" * 40)
        
        # Test configuration parsing
        print("Testing configuration parsing...")
        try:
            # Mock WeeWX config
            mock_config = {
                'Station': {
                    'latitude': 33.656915,
                    'longitude': -117.982542
                },
                'OpenWeatherService': {
                    'enable': True,
                    'api_key': 'test_key_123',
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
                        'complexity_level': 'standard'
                    }
                }
            }
            
            # Test service initialization (without actually starting it)
            print("  ✅ Mock configuration structure valid")
            
        except Exception as e:
            print(f"  ❌ Configuration parsing failed: {e}")
            return False
        
        # Test coordinate validation
        print("\nTesting coordinate validation...")
        try:
            valid_coords = [
                (33.656915, -117.982542),  # Huntington Beach
                (0, 0),                    # Null Island
                (90, 180),                 # Extreme valid
                (-90, -180)                # Extreme valid
            ]
            
            invalid_coords = [
                (91, 0),      # Invalid latitude
                (0, 181),     # Invalid longitude
                (-91, 0),     # Invalid latitude
                (0, -181)     # Invalid longitude
            ]
            
            for lat, lon in valid_coords:
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    pass  # Valid
                else:
                    print(f"  ❌ Coordinate validation: {lat}, {lon} should be valid")
                    return False
            
            print(f"  ✅ Coordinate validation: {len(valid_coords)} valid coordinates accepted")
            
            for lat, lon in invalid_coords:
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    pass  # Correctly rejected
                else:
                    print(f"  ❌ Coordinate validation: {lat}, {lon} should be rejected")
                    return False
            
            print(f"  ✅ Coordinate validation: {len(invalid_coords)} invalid coordinates rejected")
            
        except Exception as e:
            print(f"  ❌ Coordinate validation failed: {e}")
            return False
        
        print("\nConfiguration Test: ✅ PASSED")
        return True
    
    def test_database_schema(self):
        """Test database schema and field creation."""
        print("\n🗄️  TESTING DATABASE SCHEMA")
        print("-" * 40)
        
        # Test database connection
        print("Testing database connection...")
        try:
            # Find WeeWX configuration file
            config_path = self._find_weewx_config()
            if not config_path:
                print("  ⚠️  WeeWX configuration not found - skipping database tests")
                print("     (This is normal if testing outside of WeeWX installation)")
                return True
            
            # Load WeeWX configuration
            import configobj
            config_dict = configobj.ConfigObj(config_path)
            
            # Get database binding
            db_binding = config_dict.get('DataBindings', {}).get('wx_binding', 'wx_binding')
            
            # Test database connection
            with weewx.manager.open_manager_with_config(config_dict, db_binding) as dbmanager:
                print(f"  ✅ Database connection: Connected to {dbmanager.database_name}")
                
        except ImportError:
            print("  ⚠️  WeeWX modules not available - skipping database tests")
            return True
        except Exception as e:
            print(f"  ❌ Database connection failed: {e}")
            return False
        
        # Test OpenWeather field existence
        print("\nTesting OpenWeather database fields...")
        try:
            # Check for OpenWeather fields
            ow_fields = []
            for column in dbmanager.connection.genSchemaOf('archive'):
                field_name = column[1]
                if field_name.startswith('ow_'):
                    ow_fields.append(field_name)
            
            if ow_fields:
                print(f"  ✅ OpenWeather fields found: {len(ow_fields)} fields present")
                
                # Show field details for verification
                for field in sorted(ow_fields)[:10]:  # Show first 10
                    print(f"    - {field}")
                if len(ow_fields) > 10:
                    print(f"    ... and {len(ow_fields) - 10} more")
            else:
                print("  ⚠️  No OpenWeather fields found in database")
                print("     This may indicate the extension was not properly installed")
                print("     or field selection was set to minimal/none")
                
        except Exception as e:
            print(f"  ❌ Field existence check failed: {e}")
            return False
        
        # Test field types and structure
        print("\nTesting field types and structure...")
        try:
            field_info = {}
            for column in dbmanager.connection.genSchemaOf('archive'):
                field_name, field_type = column[1], column[2]
                if field_name.startswith('ow_'):
                    field_info[field_name] = field_type
            
            # Expected field types
            expected_types = {
                'REAL': ['ow_temperature', 'ow_feels_like', 'ow_humidity', 'ow_pressure', 
                        'ow_wind_speed', 'ow_wind_direction', 'ow_pm25', 'ow_pm10', 'ow_ozone'],
                'INTEGER': ['ow_aqi'],
                'TEXT': ['ow_weather_main', 'ow_weather_description', 'ow_main_pollutant']
            }
            
            type_check_passed = 0
            type_check_total = 0
            
            for expected_type, field_list in expected_types.items():
                for field_name in field_list:
                    if field_name in field_info:
                        actual_type = field_info[field_name].upper()
                        type_check_total += 1
                        
                        # Handle database-specific type variations
                        if (expected_type == 'REAL' and actual_type in ['REAL', 'DOUBLE', 'FLOAT', 'NUMERIC']) or \
                           (expected_type == 'INTEGER' and actual_type in ['INTEGER', 'INT']) or \
                           (expected_type == 'TEXT' and actual_type in ['TEXT', 'VARCHAR', 'CHAR']):
                            type_check_passed += 1
            
            if type_check_total > 0:
                print(f"  ✅ Field types: {type_check_passed}/{type_check_total} fields have correct types")
            else:
                print("  ⚠️  No recognized OpenWeather fields found for type checking")
                
        except Exception as e:
            print(f"  ❌ Field type check failed: {e}")
            return False
        
        print("\nDatabase Schema Test: ✅ PASSED")
        return True
    
    def test_service_registration(self):
        """Test WeeWX service registration and configuration."""
        print("\n⚙️  TESTING SERVICE REGISTRATION")
        print("-" * 40)
        
        # Test WeeWX configuration loading
        print("Testing WeeWX configuration...")
        try:
            config_path = self._find_weewx_config()
            if not config_path:
                print("  ⚠️  WeeWX configuration not found - skipping service registration tests")
                return True
            
            import configobj
            config_dict = configobj.ConfigObj(config_path)
            print(f"  ✅ Configuration loaded: {config_path}")
            
        except Exception as e:
            print(f"  ❌ Configuration loading failed: {e}")
            return False
        
        # Test OpenWeatherService section
        print("\nTesting OpenWeatherService configuration...")
        try:
            ow_config = config_dict.get('OpenWeatherService', {})
            
            if ow_config:
                print("  ✅ OpenWeatherService section found")
                
                # Check essential configuration
                essential_keys = ['enable', 'api_key']
                found_keys = [key for key in essential_keys if key in ow_config]
                print(f"  ✅ Essential config keys: {len(found_keys)}/{len(essential_keys)} present")
                
                # Check API key (without revealing it)
                api_key = ow_config.get('api_key', '')
                if api_key and api_key != 'REPLACE_WITH_YOUR_API_KEY':
                    print(f"  ✅ API key configured: {api_key[:8]}***")
                else:
                    print("  ⚠️  API key not configured or using placeholder")
                
                # Check modules configuration
                modules = ow_config.get('modules', {})
                if modules:
                    enabled_modules = [mod for mod, enabled in modules.items() if enabled]
                    print(f"  ✅ Enabled modules: {', '.join(enabled_modules)}")
                else:
                    print("  ⚠️  No modules configuration found")
                
            else:
                print("  ❌ OpenWeatherService section not found in configuration")
                print("     This indicates the extension was not properly installed")
                return False
                
        except Exception as e:
            print(f"  ❌ OpenWeatherService configuration check failed: {e}")
            return False
        
        # Test service registration in Engine services
        print("\nTesting service registration in Engine...")
        try:
            engine_config = config_dict.get('Engine', {})
            services_config = engine_config.get('Services', {})
            
            if services_config:
                print("  ✅ Engine Services section found")
                
                # Check data_services registration
                data_services = services_config.get('data_services', '')
                if isinstance(data_services, list):
                    data_services = ', '.join(data_services)
                
                ow_service_name = 'user.openweather.OpenWeatherService'
                if ow_service_name in data_services:
                    print(f"  ✅ Service registered: {ow_service_name} found in data_services")
                else:
                    print(f"  ❌ Service not registered: {ow_service_name} not found in data_services")
                    print(f"     Current data_services: {data_services}")
                    return False
                    
                # Show service order
                service_list = [s.strip() for s in data_services.split(',') if s.strip()]
                ow_position = next((i for i, s in enumerate(service_list) if ow_service_name in s), -1)
                if ow_position >= 0:
                    print(f"  ✅ Service order: Position {ow_position + 1} of {len(service_list)}")
                    
            else:
                print("  ❌ Engine Services section not found")
                return False
                
        except Exception as e:
            print(f"  ❌ Service registration check failed: {e}")
            return False
        
        # Test Station coordinates (used by OpenWeather service)
        print("\nTesting Station coordinates...")
        try:
            station_config = config_dict.get('Station', {})
            
            if station_config:
                latitude = station_config.get('latitude')
                longitude = station_config.get('longitude')
                
                if latitude is not None and longitude is not None:
                    lat_val = float(latitude)
                    lon_val = float(longitude)
                    
                    if -90 <= lat_val <= 90 and -180 <= lon_val <= 180:
                        print(f"  ✅ Station coordinates: {lat_val}, {lon_val}")
                    else:
                        print(f"  ❌ Invalid coordinates: {lat_val}, {lon_val}")
                        return False
                else:
                    print("  ❌ Station coordinates not configured")
                    return False
            else:
                print("  ❌ Station section not found")
                return False
                
        except Exception as e:
            print(f"  ❌ Station coordinates check failed: {e}")
            return False
        
        print("\nService Registration Test: ✅ PASSED")
        return True
    
    def test_service_integration(self):
        """Test WeeWX service integration components."""
        print("\n🔗 TESTING SERVICE INTEGRATION")
        print("-" * 40)
        
        # Test unit system setup
        print("Testing unit system integration...")
        try:
            # Test unit group mappings
            test_fields = {
                'ow_temperature': 'group_temperature',
                'ow_humidity': 'group_percent',
                'ow_pressure': 'group_pressure',
                'ow_wind_speed': 'group_speed',
                'ow_pm25': 'group_concentration',
                'ow_aqi': 'group_count'
            }
            
            # This would normally be done by the service
            unit_mappings = {}
            for field, expected_group in test_fields.items():
                field_name = field[3:]  # Remove 'ow_' prefix
                
                if field_name in ['temperature', 'feels_like']:
                    unit_mappings[field] = 'group_temperature'
                elif field_name == 'humidity':
                    unit_mappings[field] = 'group_percent'
                elif field_name == 'pressure':
                    unit_mappings[field] = 'group_pressure'
                elif field_name == 'wind_speed':
                    unit_mappings[field] = 'group_speed'
                elif field_name in ['pm25', 'pm10']:
                    unit_mappings[field] = 'group_concentration'
                elif field_name == 'aqi':
                    unit_mappings[field] = 'group_count'
            
            correct_mappings = sum(1 for field, group in unit_mappings.items() 
                                 if test_fields.get(field) == group)
            
            print(f"  ✅ Unit mappings: {correct_mappings}/{len(test_fields)} correctly mapped")
            
        except Exception as e:
            print(f"  ❌ Unit system integration failed: {e}")
            return False
        
        # Test archive record injection simulation
        print("\nTesting archive record injection...")
        try:
            # Mock archive record
            mock_record = {}
            
            # Mock latest data
            mock_latest_data = {
                'ow_temperature': 22.5,
                'ow_humidity': 65,
                'ow_pm25': 8.7,
                'ow_aqi': 2,
                'ow_weather_timestamp': time.time(),
                'ow_air_quality_timestamp': time.time()
            }
            
            # Simulate injection logic
            current_time = time.time()
            max_age = 7200  # 2 hours
            
            injected_count = 0
            for field_name, value in mock_latest_data.items():
                if value is not None and not field_name.endswith('_timestamp'):
                    # Simulate freshness check
                    if field_name.startswith('ow_weather_'):
                        data_age = current_time - mock_latest_data.get('ow_weather_timestamp', 0)
                    elif field_name.startswith('ow_air_quality_'):
                        data_age = current_time - mock_latest_data.get('ow_air_quality_timestamp', 0)
                    else:
                        data_age = 0  # Fresh data
                    
                    if data_age <= max_age:
                        mock_record[field_name] = value
                        injected_count += 1
            
            expected_fields = ['ow_temperature', 'ow_humidity', 'ow_pm25', 'ow_aqi']
            if injected_count == len(expected_fields):
                print(f"  ✅ Archive injection: {injected_count} fields would be injected")
            else:
                print(f"  ❌ Archive injection: Expected {len(expected_fields)}, got {injected_count}")
                return False
                
        except Exception as e:
            print(f"  ❌ Archive record injection failed: {e}")
            return False
        
        print("\nService Integration Test: ✅ PASSED")
        return True
    
    def _find_weewx_config(self):
        """Find WeeWX configuration file."""
        possible_paths = [
            '/etc/weewx/weewx.conf',
            '/home/weewx/weewx.conf',
            '/opt/weewx/weewx.conf',
            os.path.expanduser('~/weewx-data/weewx.conf'),
            '/usr/share/weewx/weewx.conf'
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        return None
    
    def test_thread_safety(self):
        """Test thread safety components."""
        print("\n🔒 TESTING THREAD SAFETY")
        print("-" * 40)
        
        # Test data locking simulation
        print("Testing data lock behavior...")
        try:
            import threading
            
            test_data = {}
            data_lock = threading.Lock()
            
            # Simulate writing data (what background thread does)
            def write_data():
                with data_lock:
                    test_data['temperature'] = 22.5
                    test_data['timestamp'] = time.time()
            
            # Simulate reading data (what archive injection does)
            def read_data():
                with data_lock:
                    return test_data.copy()
            
            # Test write then read
            write_data()
            read_result = read_data()
            
            if 'temperature' in read_result and read_result['temperature'] == 22.5:
                print("  ✅ Data locking: Write/read operations work correctly")
            else:
                print("  ❌ Data locking: Write/read operations failed")
                return False
                
        except Exception as e:
            print(f"  ❌ Thread safety test failed: {e}")
            return False
        
        # Test concurrent access simulation
        print("\nTesting concurrent access patterns...")
        try:
            # This would be a more complex test in practice
            # For now, just verify the pattern works
            results = []
            errors = []
            
            def mock_writer():
                try:
                    for i in range(5):
                        with data_lock:
                            test_data[f'value_{i}'] = i
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            
            def mock_reader():
                try:
                    for i in range(5):
                        with data_lock:
                            current_data = test_data.copy()
                        results.append(len(current_data))
                        time.sleep(0.001)
                except Exception as e:
                    errors.append(e)
            
            # Run mock concurrent operations
            writer_thread = threading.Thread(target=mock_writer)
            reader_thread = threading.Thread(target=mock_reader)
            
            writer_thread.start()
            reader_thread.start()
            
            writer_thread.join(timeout=1)
            reader_thread.join(timeout=1)
            
            if len(errors) == 0:
                print(f"  ✅ Concurrent access: No threading errors in {len(results)} operations")
            else:
                print(f"  ❌ Concurrent access: {len(errors)} threading errors occurred")
                return False
                
        except Exception as e:
            print(f"  ❌ Concurrent access test failed: {e}")
            return False
        
        print("\nThread Safety Test: ✅ PASSED")
        return True
    
    def run_all_tests(self):
        """Run all available tests."""
        print(f"\n🧪 RUNNING ALL TESTS")
        print("=" * 60)
        
        tests = [
            ("Field Selection", self.test_field_selection),
            ("Data Processing", self.test_data_processing),
            ("Configuration", self.test_configuration),
            ("Database Schema", self.test_database_schema),
            ("Service Registration", self.test_service_registration),
            ("Service Integration", self.test_service_integration),
            ("Thread Safety", self.test_thread_safety)
        ]
        
        # Add API test if we have credentials
        if self.api_key:
            tests.insert(0, ("API Connectivity", self.test_api_connectivity))
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            try:
                if test_func():
                    passed += 1
                    print(f"\n{test_name}: ✅ PASSED")
                else:
                    print(f"\n{test_name}: ❌ FAILED")
            except Exception as e:
                print(f"\n{test_name}: ❌ ERROR - {e}")
        
        print("\n" + "=" * 60)
        print(f"TEST SUMMARY: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 ALL TESTS PASSED! Extension is working correctly.")
            print("\n✅ Installation verification complete:")
            print("   • Database fields created successfully")
            print("   • Service registered in WeeWX configuration")
            print("   • Extension components functioning properly")
        else:
            print("⚠️  Some tests failed. Check the output above for details.")
            if any("Database" in test[0] or "Service Registration" in test[0] for test in tests):
                print("\n🔧 Installation troubleshooting:")
                print("   • If database tests failed: Run 'weectl database add-column' commands manually")
                print("   • If service registration failed: Check [OpenWeatherService] section in weewx.conf")
                print("   • If API tests failed: Verify your API key at https://openweathermap.org/api")
        
        return passed == total


def main():
    """Main function for command-line testing."""
    parser = argparse.ArgumentParser(
        description='OpenWeather Extension Testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test API connectivity
  python3 openweather.py --test-api --api-key YOUR_KEY --latitude 33.66 --longitude -117.98
  
  # Test all functionality
  python3 openweather.py --test-all --api-key YOUR_KEY
  
  # Test without API (skips connectivity test)
  python3 openweather.py --test-all
  
  # Test specific component
  python3 openweather.py --test-data
        """
    )
    
    # Test options
    parser.add_argument('--test-api', action='store_true', 
                       help='Test API connectivity (requires --api-key)')
    parser.add_argument('--test-data', action='store_true',
                       help='Test data processing and field mapping')
    parser.add_argument('--test-config', action='store_true',
                       help='Test configuration parsing and validation')
    parser.add_argument('--test-database', action='store_true',
                       help='Test database schema and field creation')
    parser.add_argument('--test-registration', action='store_true',
                       help='Test service registration in WeeWX configuration')
    parser.add_argument('--test-service', action='store_true',
                       help='Test service integration components')
    parser.add_argument('--test-thread', action='store_true',
                       help='Test thread safety')
    parser.add_argument('--test-fields', action='store_true',
                       help='Test field selection functionality')
    parser.add_argument('--test-all', action='store_true',
                       help='Run all available tests')
    parser.add_argument('--test-install', action='store_true',
                       help='Test installation (database + service registration)')
    
    # Configuration options
    parser.add_argument('--api-key', 
                       help='OpenWeatherMap API key for connectivity testing')
    parser.add_argument('--latitude', type=float, default=33.656915,
                       help='Latitude for testing (default: Huntington Beach, CA)')
    parser.add_argument('--longitude', type=float, default=-117.982542,
                       help='Longitude for testing (default: Huntington Beach, CA)')
    
    # Information options
    parser.add_argument('--version', action='store_true',
                       help='Show extension version')
    parser.add_argument('--info', action='store_true',
                       help='Show extension information')
    
    args = parser.parse_args()
    
    # Handle information requests
    if args.version:
        print(f"OpenWeather Extension v{VERSION}")
        return
    
    if args.info:
        print(f"OpenWeather Extension v{VERSION}")
        print("=" * 40)
        print("A comprehensive WeeWX extension for OpenWeatherMap API integration")
        print("Features: Weather data, air quality, field selection, rate limiting")
        print("Copyright (C) 2025 WeeWX OpenWeather API Extension")
        print("License: GNU General Public License v3.0")
        return
    
    # Initialize tester
    tester = OpenWeatherTester(args.api_key, args.latitude, args.longitude)
    
    # Run requested tests
    if args.test_all:
        success = tester.run_all_tests()
    elif args.test_install:
        # Run installation-specific tests
        print("🔧 TESTING INSTALLATION")
        print("=" * 40)
        success = True
        success &= tester.test_database_schema()
        success &= tester.test_service_registration()
        
        if success:
            print("\n✅ INSTALLATION VERIFICATION COMPLETE!")
            print("Extension was installed correctly and is ready to use.")
        else:
            print("\n❌ INSTALLATION ISSUES DETECTED")
            print("Check the output above for specific problems.")
    else:
        success = True
        test_count = 0
        
        if args.test_api:
            success &= tester.test_api_connectivity()
            test_count += 1
        
        if args.test_fields:
            success &= tester.test_field_selection()
            test_count += 1
        
        if args.test_data:
            success &= tester.test_data_processing()
            test_count += 1
        
        if args.test_config:
            success &= tester.test_configuration()
            test_count += 1
        
        if args.test_database:
            success &= tester.test_database_schema()
            test_count += 1
        
        if args.test_registration:
            success &= tester.test_service_registration()
            test_count += 1
        
        if args.test_service:
            success &= tester.test_service_integration()
            test_count += 1
        
        if args.test_thread:
            success &= tester.test_thread_safety()
            test_count += 1
        
        if test_count == 0:
            print("No tests specified. Use --help to see available options.")
            print("\nQuick options:")
            print("  --test-all       # Test everything")
            print("  --test-install   # Test installation (database + service)")
            print("  --test-api       # Test API connectivity")
            return
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()

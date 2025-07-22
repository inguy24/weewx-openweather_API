#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension - Enhanced with Field Selection System

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
                        if field_name in fields:
                            mappings[field_info['database_field']] = field_info['database_type']
        
        return mappings
    
    def get_api_path_mappings(self, selected_fields):
        """Get API path mappings for selected fields."""
        mappings = {}
        all_fields = self.get_all_available_fields()
        
        for module, fields in selected_fields.items():
            if module in all_fields:
                for category_data in all_fields[module]['categories'].values():
                    for field_name, field_info in category_data['fields'].items():
                        if field_name in fields:
                            mappings[field_info['database_field']] = field_info['api_path']
        
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
        
        # Otherwise use custom field selection
        custom_selection = {
            'current_weather': field_config.get('current_weather', []),
            'air_quality': field_config.get('air_quality', [])
        }
        
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
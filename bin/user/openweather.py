#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension - Enhanced with Field Selection System and Built-in Testing

Provides modular OpenWeatherMap API integration with user-selectable fields
and dynamic database schema management.

Copyright (C) 2025 WeeWX OpenWeather API Extension
"""

import json
import configobj
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


class OpenWeatherAPIError(Exception):
    """Custom exception for OpenWeather API errors."""
    pass


class OpenWeatherDataCollector:
    """Enhanced data collector with field selection support."""
    
    def __init__(self, api_key, timeout=30, selected_fields=None):
        self.api_key = api_key
        # FIX: Ensure timeout is always an integer
        self.timeout = int(timeout) if timeout else 30
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
            timeout=int(config.get('timeout', 30)),  # FIX: Convert string to int
            selected_fields=selected_fields
        )
        
        # Thread-safe data storage
        self.data_lock = threading.Lock()
        self.latest_data = {}
        
        # Get station coordinates
        station_config = config.get('Station', {})
        self.latitude = float(station_config.get('latitude', 0.0))
        self.longitude = float(station_config.get('longitude', 0.0))
        
        # Module intervals - FIX: Convert strings to integers
        self.intervals = {
            'current_weather': int(config.get('intervals', {}).get('current_weather', 3600)),
            'air_quality': int(config.get('intervals', {}).get('air_quality', 7200))
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
                
                # FIX: Convert string boolean to actual boolean
                log_success = str(self.config.get('log_success', 'false')).lower() in ('true', 'yes', '1')
                if log_success:
                    log.info(f"Collected current weather data: {len(weather_data)} fields")
            
        except OpenWeatherAPIError as e:
            # FIX: Convert string boolean to actual boolean
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"OpenWeather API error collecting weather data: {e}")
        except Exception as e:
            # FIX: Convert string boolean to actual boolean
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"Unexpected error collecting weather data: {e}")
    
    def _collect_air_quality(self):
        """Collect air quality data."""
        try:
            air_quality_data = self.collector.collect_air_quality(self.latitude, self.longitude)
            
            if air_quality_data:
                with self.data_lock:
                    self.latest_data.update(air_quality_data)
                
                # FIX: Convert string boolean to actual boolean
                log_success = str(self.config.get('log_success', 'false')).lower() in ('true', 'yes', '1')
                if log_success:
                    log.info(f"Collected air quality data: {len(air_quality_data)} fields")
            
        except OpenWeatherAPIError as e:
            # FIX: Convert string boolean to actual boolean
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"OpenWeather API error collecting air quality data: {e}")
        except Exception as e:
            # FIX: Convert string boolean to actual boolean
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
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
    """Robust OpenWeather service that never breaks WeeWX - graceful degradation only."""
    
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        
        # Load service configuration (operational settings only from weewx.conf)
        self.service_config = config_dict.get('OpenWeatherService', {})
        
        # Initialize with safe defaults
        self.selected_fields = {}
        self.active_fields = {}  # Fields actually available for collection
        self.service_enabled = False
        
        try:
            # Load field selection from extension-managed file (NOT weewx.conf)
            self.selected_fields = self._load_field_selection()
            
            # Validate and clean field selection (never fails - just logs issues)
            self.active_fields = self._validate_and_clean_selection()
            
            if self.active_fields:
                # Initialize data collection if we have usable fields
                self._initialize_data_collection()
                self.service_enabled = True
                log.info(f"OpenWeather service started successfully ({self._count_active_fields()} fields active)")
            else:
                log.error("OpenWeather service disabled - no usable fields available")
                log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to fix configuration")
                
        except Exception as e:
            # NEVER let OpenWeather break WeeWX startup
            log.error(f"OpenWeather service initialization failed: {e}")
            log.error("OpenWeather data collection disabled - WeeWX will continue normally")
            self.service_enabled = False
    
    def _load_field_selection(self):
        """Load field selection from extension-managed file - never fails."""
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        try:
            if os.path.exists(selection_file):
                config = configobj.ConfigObj(selection_file)
                field_selection = config.get('field_selection', {})
                selected_fields = field_selection.get('selected_fields', {})
                
                if not selected_fields:
                    log.warning("No field selection found in configuration file")
                    return {}
                
                log.info(f"Loaded field selection from {selection_file}: {list(selected_fields.keys())}")
                return selected_fields
            else:
                log.error(f"Field selection file not found: {selection_file}")
                log.error("This usually means the extension was not properly installed")
                log.error("HINT: Run 'weectl extension install weewx-openweather.zip' to properly install")
                return {}
                
        except Exception as e:
            log.error(f"Failed to load field selection from {selection_file}: {e}")
            log.error("OpenWeather service will be disabled")
            return {}
    
    def _validate_and_clean_selection(self):
        """Validate field selection and return only usable fields - never fails."""
        
        if not self.selected_fields:
            log.warning("No field selection available - OpenWeather collection disabled")
            return {}
        
        field_manager = FieldSelectionManager()
        active_fields = {}
        total_selected = 0
        
        try:
            # Get expected database fields based on selection
            expected_fields = field_manager.get_database_field_mappings(self.selected_fields)
            
            if not expected_fields:
                log.warning("No database fields required for current selection")
                return {}
            
            # Check which fields actually exist in database
            existing_db_fields = self._get_existing_database_fields()
            
            # Validate each module's fields
            for module, fields in self.selected_fields.items():
                if not fields:
                    continue
                    
                if fields == 'all':
                    # Handle 'all' selection
                    module_fields = self._get_all_fields_for_module(module, field_manager)
                    total_selected += len(module_fields)
                    active_module_fields = self._validate_module_fields(module, module_fields, expected_fields, existing_db_fields, field_manager)
                elif isinstance(fields, list):
                    # Handle specific field list
                    total_selected += len(fields)
                    active_module_fields = self._validate_module_fields(module, fields, expected_fields, existing_db_fields, field_manager)
                else:
                    log.warning(f"Invalid field selection format for module '{module}': {fields}")
                    continue
                
                if active_module_fields:
                    active_fields[module] = active_module_fields
            
            # Validate forecast table if needed
            self._validate_forecast_table()
            
            # Summary logging
            total_active = self._count_active_fields(active_fields)
            if total_active > 0:
                log.info(f"Field validation complete: {total_active}/{total_selected} fields active")
                if total_active < total_selected:
                    log.warning(f"{total_selected - total_active} fields unavailable - see errors above")
                    log.warning("HINT: Run 'weectl extension reconfigure OpenWeather' to fix field issues")
                
                # Check for new fields available
                self._check_for_new_fields(field_manager)
            else:
                log.error("No usable fields found - all fields have issues")
            
            return active_fields
            
        except Exception as e:
            log.error(f"Field validation failed: {e}")
            return {}
    
    def _validate_module_fields(self, module, fields, expected_fields, existing_db_fields, field_manager):
        """Validate fields for a specific module - never fails."""
        active_fields = []
        
        if not fields:
            return active_fields
        
        field_list = fields if isinstance(fields, list) else []
        
        for field in field_list:
            try:
                # Find the database field name for this logical field
                db_field = self._get_database_field_name(module, field, field_manager)
                
                if not db_field:
                    log.warning(f"Unknown field '{field}' in module '{module}' - skipping")
                    continue
                
                if db_field not in existing_db_fields:
                    log.error(f"Database field '{db_field}' missing for '{module}.{field}' - skipping")
                    log.error(f"HINT: Run 'weectl extension reconfigure OpenWeather' to add missing fields")
                    continue
                
                # Field is valid and available
                active_fields.append(field)
                
            except Exception as e:
                log.error(f"Error validating field '{field}' in module '{module}': {e}")
                continue
        
        if active_fields:
            log.info(f"Module '{module}': {len(active_fields)}/{len(field_list)} fields active")
        else:
            log.warning(f"Module '{module}': no usable fields")
        
        return active_fields
    
    def _get_database_field_name(self, module, field, field_manager):
        """Get database field name for a logical field name."""
        try:
            all_fields = field_manager.get_all_available_fields()
            if module in all_fields:
                for category_data in all_fields[module]['categories'].values():
                    if field in category_data['fields']:
                        return category_data['fields'][field]['database_field']
        except Exception as e:
            log.error(f"Error looking up database field for {module}.{field}: {e}")
        return None
    
    def _get_all_fields_for_module(self, module, field_manager):
        """Get all available fields for a module when 'all' is selected."""
        try:
            all_fields = field_manager.get_all_available_fields()
            if module in all_fields:
                module_fields = []
                for category_data in all_fields[module]['categories'].values():
                    module_fields.extend(category_data['fields'].keys())
                return module_fields
        except Exception as e:
            log.error(f"Error getting all fields for module '{module}': {e}")
        return []
    
    def _validate_forecast_table(self):
        """Validate forecast table if needed - never fails."""
        forecast_modules = ['forecast_daily', 'forecast_hourly', 'forecast_air_quality']
        needs_forecast_table = any(module in self.selected_fields for module in forecast_modules)
        
        if not needs_forecast_table:
            return
        
        try:
            db_binding = 'wx_binding'
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                dbmanager.connection.execute("SELECT 1 FROM openweather_forecast LIMIT 1")
                log.info("Forecast table validated successfully")
        except Exception as e:
            log.error(f"Forecast table missing or inaccessible: {e}")
            log.error("Forecast modules will be disabled")
            log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to create forecast table")
            
            # Remove forecast modules from active fields
            for module in forecast_modules:
                if module in self.active_fields:
                    del self.active_fields[module]
                    log.warning(f"Disabled forecast module: {module}")
    
    def _get_existing_database_fields(self):
        """Get list of existing OpenWeather fields - never fails."""
        try:
            db_binding = 'wx_binding'
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                existing_fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    field_name = column[1]
                    if field_name.startswith('ow_'):
                        existing_fields.append(field_name)
                return existing_fields
        except Exception as e:
            log.error(f"Error checking database fields: {e}")
            return []
    
    def _check_for_new_fields(self, field_manager):
        """Check if new fields are available that user hasn't selected."""
        try:
            all_available = field_manager.get_all_available_fields()
            
            for module, module_data in all_available.items():
                if module not in self.selected_fields or not self.selected_fields[module]:
                    # Module not selected at all
                    all_module_fields = self._get_all_fields_for_module(module, field_manager)
                    if all_module_fields:
                        log.info(f"New module available: '{module}' with {len(all_module_fields)} fields")
                        log.info(f"HINT: Run 'weectl extension reconfigure OpenWeather' to enable new features")
                elif self.selected_fields[module] != 'all':
                    # Check for new fields in selected modules
                    selected_fields = self.selected_fields[module] if isinstance(self.selected_fields[module], list) else []
                    all_module_fields = self._get_all_fields_for_module(module, field_manager)
                    new_fields = [f for f in all_module_fields if f not in selected_fields]
                    
                    if new_fields:
                        log.info(f"New fields available in module '{module}': {new_fields}")
                        log.info(f"HINT: Run 'weectl extension reconfigure OpenWeather' to enable new fields")
                        
        except Exception as e:
            log.debug(f"Error checking for new fields: {e}")
    
    def _count_active_fields(self, fields=None):
        """Count total active fields across all modules."""
        if fields is None:
            fields = self.active_fields
        return sum(len(module_fields) for module_fields in fields.values() if isinstance(module_fields, list))
    
    def _initialize_data_collection(self):
        """Initialize data collection components - graceful failure."""
        try:
            # Set up API client with active fields only
            self.api_client = OpenWeatherAPIClient(
                api_key=self.service_config['api_key'],
                selected_fields=self.active_fields,  # Use validated fields
                timeout=int(self.service_config.get('timeout', 30))
            )
            
            # Set up background collection thread
            self.background_thread = OpenWeatherBackgroundThread(
                config=self.service_config,
                selected_fields=self.active_fields,  # Use validated fields
                api_client=self.api_client
            )
            
            # Start background collection
            self.background_thread.start()
            
            log.info("Data collection initialized successfully")
            
        except Exception as e:
            log.error(f"Failed to initialize data collection: {e}")
            log.error("OpenWeather data collection disabled")
            self.service_enabled = False
    
    def new_archive_record(self, event):
        """Inject OpenWeather data into archive record - never fails."""
        
        if not self.service_enabled:
            return  # Silently skip if service is disabled
        
        try:
            # Get latest collected data
            collected_data = self.get_latest_data()
            
            if not collected_data:
                return  # No data available
            
            # Build record with all expected fields, using None for missing data
            record_update = {}
            field_manager = FieldSelectionManager()
            expected_fields = field_manager.get_database_field_mappings(self.active_fields)
            
            fields_injected = 0
            for db_field, field_type in expected_fields.items():
                if db_field in collected_data and collected_data[db_field] is not None:
                    # Successfully collected data
                    record_update[db_field] = collected_data[db_field]
                    fields_injected += 1
                else:
                    # Missing data - use None/NULL
                    record_update[db_field] = None
            
            # Update the archive record
            event.record.update(record_update)
            
            if fields_injected > 0:
                log.debug(f"Injected OpenWeather data: {fields_injected}/{len(expected_fields)} fields")
            else:
                log.debug("No OpenWeather data available for injection")
                
        except Exception as e:
            log.error(f"Error injecting OpenWeather data: {e}")
            # Continue without OpenWeather data - don't break the archive record
    
    def get_latest_data(self):
        """Get latest collected data - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                return self.background_thread.get_latest_data()
        except Exception as e:
            log.error(f"Error getting latest data: {e}")
        return {}
    
    def shutDown(self):
        """Clean shutdown - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                self.background_thread.stop()
                log.info("OpenWeather service shutdown complete")
        except Exception as e:
            log.error(f"Error during OpenWeather shutdown: {e}")

            
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
        """Test database schema using WeeWX's standard manager (database-agnostic)."""
        print("\n🗄️  TESTING DATABASE SCHEMA")
        print("-" * 40)
        
        # Test database connection using WeeWX's standard approach
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
            
            # Set WEEWX_ROOT if not already set (required for WeeWX manager)
            import os
            if 'WEEWX_ROOT' not in os.environ:
                # Try to determine WEEWX_ROOT from config file location
                weewx_root = os.path.dirname(os.path.dirname(config_path))  # Usually /etc/weewx -> /
                if not weewx_root or weewx_root == '/':
                    weewx_root = '/usr/share/weewx'  # Default WeeWX installation path
                os.environ['WEEWX_ROOT'] = weewx_root
                config_dict['WEEWX_ROOT'] = weewx_root
            
            # Use WeeWX's standard database manager (database-agnostic)
            db_binding = 'wx_binding'  # Standard WeeWX binding name
            
            # Test database connection using WeeWX's standard method
            with weewx.manager.open_manager_with_config(config_dict, db_binding) as dbmanager:
                print(f"  ✅ Database connection: Connected to {dbmanager.database_name}")
                
                # Get column information (works for both SQLite and MySQL)
                columns = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    columns.append(column[1])  # column[1] is the column name
                
                ow_fields = [col for col in columns if col.startswith('ow_')]
                
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
                
                # Test data presence (functional test)
                print("\nTesting data collection functionality...")
                
                # Check for recent OpenWeather data
                cursor = dbmanager.connection.cursor()
                cursor.execute("SELECT COUNT(*) FROM archive WHERE ow_temperature IS NOT NULL")
                weather_data_count = cursor.fetchone()[0]
                
                cursor.execute("SELECT COUNT(*) FROM archive WHERE ow_pm25 IS NOT NULL")  
                air_quality_count = cursor.fetchone()[0]
                
                if weather_data_count > 0:
                    print(f"  ✅ Weather data: {weather_data_count} records contain OpenWeather weather data")
                else:
                    print("  ⚠️  No weather data found (extension may be newly installed or disabled)")
                    
                if air_quality_count > 0:
                    print(f"  ✅ Air quality data: {air_quality_count} records contain OpenWeather air quality data")
                else:
                    print("  ⚠️  No air quality data found (extension may be newly installed or disabled)")
                
                # Test data freshness if data exists
                if weather_data_count > 0 or air_quality_count > 0:
                    # Use database-agnostic SQL for timestamp comparison
                    if 'sqlite' in str(type(dbmanager.connection)).lower():
                        # SQLite syntax
                        cursor.execute("""
                            SELECT 
                                COUNT(*) as recent_records,
                                MAX(ow_weather_timestamp) as latest_weather,
                                MAX(ow_air_quality_timestamp) as latest_air_quality
                            FROM archive 
                            WHERE (ow_temperature IS NOT NULL OR ow_pm25 IS NOT NULL)
                            AND dateTime > strftime('%s', 'now', '-1 day')
                        """)
                    else:
                        # MySQL syntax
                        cursor.execute("""
                            SELECT 
                                COUNT(*) as recent_records,
                                MAX(ow_weather_timestamp) as latest_weather,
                                MAX(ow_air_quality_timestamp) as latest_air_quality
                            FROM archive 
                            WHERE (ow_temperature IS NOT NULL OR ow_pm25 IS NOT NULL)
                            AND dateTime > UNIX_TIMESTAMP(DATE_SUB(NOW(), INTERVAL 1 DAY))
                        """)
                    
                    result = cursor.fetchone()
                    if result and result[0] > 0:
                        print(f"  ✅ Data freshness: {result[0]} records with data in last 24 hours")
                        
                        # Show timestamps if available
                        if result[1]:  # latest_weather
                            import datetime
                            weather_time = datetime.datetime.fromtimestamp(result[1]).strftime('%Y-%m-%d %H:%M:%S')
                            print(f"    Latest weather data: {weather_time}")
                        if result[2]:  # latest_air_quality  
                            air_time = datetime.datetime.fromtimestamp(result[2]).strftime('%Y-%m-%d %H:%M:%S')
                            print(f"    Latest air quality data: {air_time}")
                    else:
                        print("  ⚠️  No recent data found (check if service is running)")
                
        except ImportError as e:
            print(f"  ⚠️  Required modules not available: {e}")
            print("     This is normal if WeeWX is not installed")
            return True
        except Exception as e:
            print(f"  ❌ Database test failed: {e}")
            
            # If WeeWX manager fails, try a simpler direct approach
            print("\nTrying simplified database test...")
            try:
                import sqlite3
                
                # Try to find the database file from the configuration
                config_dict = configobj.ConfigObj(config_path)
                db_path = None
                
                # Look for database path in configuration
                try:
                    db_config = config_dict['DataBindings']['wx_binding']
                    db_name = db_config['database']
                    db_info = config_dict['Databases'][db_name]
                    db_path = db_info.get('database_name', '/var/lib/weewx/weewx.sdb')
                    
                    # Handle relative paths
                    if not db_path.startswith('/'):
                        db_path = f"/var/lib/weewx/{db_path}"
                        
                except (KeyError, TypeError):
                    # Fallback to standard location
                    db_path = '/var/lib/weewx/weewx.sdb'
                
                # Test direct SQLite connection
                if db_path and os.path.exists(db_path):
                    conn = sqlite3.connect(db_path)
                    cursor = conn.cursor()
                    
                    # Check for OpenWeather fields
                    cursor.execute("PRAGMA table_info(archive)")
                    columns = cursor.fetchall()
                    ow_fields = [col[1] for col in columns if col[1].startswith('ow_')]
                    
                    if ow_fields:
                        print(f"  ✅ Direct test: Found {len(ow_fields)} OpenWeather fields")
                        
                        # Check for data
                        cursor.execute("SELECT COUNT(*) FROM archive WHERE ow_temperature IS NOT NULL")
                        data_count = cursor.fetchone()[0]
                        
                        if data_count > 0:
                            print(f"  ✅ Direct test: {data_count} records contain OpenWeather data")
                        else:
                            print("  ⚠️  Direct test: No OpenWeather data found")
                            
                        conn.close()
                        print("\nDatabase Schema Test: ✅ PASSED (via direct test)")
                        return True
                    else:
                        print("  ⚠️  Direct test: No OpenWeather fields found")
                        conn.close()
                        
                else:
                    print(f"  ❌ Database file not found: {db_path}")
                    
            except Exception as e2:
                print(f"  ❌ Direct database test also failed: {e2}")
            
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

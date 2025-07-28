#!/usr/bin/env python3
# Magic Animal: Kangaroo

"""
WeeWX OpenWeather Extension - Enhanced with Field Selection System and Built-in Testing

Provides modular OpenWeatherMap API integration with user-selectable fields
and dynamic database schema management.

Copyright (C) 2025 Shane Burkhardt
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
    """Manages field selection using configuration data (no YAML at runtime)."""
    
    def __init__(self, config_dict=None):
        self.config_dict = config_dict
        
    def get_database_field_mappings(self, selected_fields):
        """Convert field selection to database field mappings using conf data only."""
        mappings = {}
        
        if not self.config_dict:
            log.error("No configuration data available for field mappings")
            return mappings
            
        service_config = self.config_dict.get('OpenWeatherService', {})
        if not service_config:
            log.error("No OpenWeatherService configuration found")
            return mappings
            
        field_mappings = service_config.get('field_mappings', {})
        if not field_mappings:
            log.error("No field_mappings found in service configuration")
            return mappings
        
        # Extract database fields from conf mappings - NO FALLBACKS
        for module_name, field_list in selected_fields.items():
            if isinstance(field_list, list):
                module_mappings = field_mappings.get(module_name, {})
                if not module_mappings:
                    log.error(f"No field mappings found for module '{module_name}'")
                    continue
                    
                for service_field in field_list:
                    field_mapping = module_mappings.get(service_field, {})
                    if not isinstance(field_mapping, dict):
                        log.error(f"Invalid field mapping for {module_name}.{service_field}: {field_mapping}")
                        continue
                        
                    db_field = field_mapping.get('database_field')
                    db_type = field_mapping.get('database_type')
                    
                    if not db_field:
                        log.error(f"No database_field defined for {module_name}.{service_field}")
                        continue
                        
                    if not db_type:
                        log.error(f"No database_type defined for {module_name}.{service_field}")
                        continue
                        
                    mappings[db_field] = db_type
        
        return mappings

    def _map_service_to_database_field(self, service_field, module_name):
        """Map service field name to database field name using CONF data only."""
        try:
            if not self.config_dict:
                log.error(f"No configuration data available for field mapping: {service_field}")
                return None
                
            service_config = self.config_dict.get('OpenWeatherService', {})
            if not service_config:
                log.error(f"No OpenWeatherService configuration found for field mapping: {service_field}")
                return None
                
            field_mappings = service_config.get('field_mappings', {})
            if not field_mappings:
                log.error(f"No field_mappings found in configuration for field: {service_field}")
                return None
                
            module_mappings = field_mappings.get(module_name, {})
            if not module_mappings:
                log.error(f"No field mappings found for module '{module_name}' and field '{service_field}'")
                return None
                
            field_mapping = module_mappings.get(service_field, {})
            if not isinstance(field_mapping, dict):
                log.error(f"Invalid field mapping for {module_name}.{service_field}: {field_mapping}")
                return None
                
            database_field = field_mapping.get('database_field')
            if not database_field:
                log.error(f"No database_field defined for {module_name}.{service_field}")
                return None
                
            return database_field
            
        except Exception as e:
            log.error(f"Error mapping service field {service_field}: {e}")
            return None


class OpenWeatherAPIError(Exception):
    """Custom exception for OpenWeather API errors."""
    pass


class OpenWeatherDataCollector:
    """API client for OpenWeather data collection with field selection support."""
    
    def __init__(self, api_key, timeout=30, selected_fields=None, config_dict=None):
        self.api_key = api_key
        self.timeout = int(timeout) if timeout else 30
        self.selected_fields = selected_fields or {}
        self.config_dict = config_dict
        
        self.base_urls = {
            'current_weather': 'http://api.openweathermap.org/data/2.5/weather',
            'air_quality': 'http://api.openweathermap.org/data/2.5/air_pollution'
        }

    def collect_current_weather(self, latitude, longitude):
        """Collect current weather data from OpenWeather API."""
        if not self.api_key:
            raise OpenWeatherAPIError("No API key configured")
        
        url = f"{self.base_urls['current_weather']}?lat={latitude}&lon={longitude}&appid={self.api_key}&units=metric"
        
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    raise OpenWeatherAPIError(f"API returned status {response.getcode()}")
                
                data = json.loads(response.read().decode('utf-8'))
                return self._extract_weather_data(data)
                
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise OpenWeatherAPIError("Invalid API key")
            elif e.code == 404:
                raise OpenWeatherAPIError("Location not found")
            else:
                raise OpenWeatherAPIError(f"HTTP error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise OpenWeatherAPIError(f"Network error: {e.reason}")
        except socket.timeout:
            raise OpenWeatherAPIError("Request timeout")
        except json.JSONDecodeError as e:
            raise OpenWeatherAPIError(f"Invalid JSON response: {e}")

    def collect_air_quality(self, latitude, longitude):
        """Collect air quality data from OpenWeather API."""
        if not self.api_key:
            raise OpenWeatherAPIError("No API key configured")
        
        url = f"{self.base_urls['air_quality']}?lat={latitude}&lon={longitude}&appid={self.api_key}"
        
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.getcode() != 200:
                    raise OpenWeatherAPIError(f"API returned status {response.getcode()}")
                
                data = json.loads(response.read().decode('utf-8'))
                return self._extract_air_quality_data(data)
                
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise OpenWeatherAPIError("Invalid API key")
            elif e.code == 404:
                raise OpenWeatherAPIError("Location not found")
            else:
                raise OpenWeatherAPIError(f"HTTP error {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise OpenWeatherAPIError(f"Network error: {e.reason}")
        except socket.timeout:
            raise OpenWeatherAPIError("Request timeout")
        except json.JSONDecodeError as e:
            raise OpenWeatherAPIError(f"Invalid JSON response: {e}")

    def collect_all_data(self, latitude, longitude):
        """Collect data from all required APIs based on selected fields."""
        all_data = {}
        
        if self.selected_fields.get('current_weather'):
            try:
                weather_data = self.collect_current_weather(latitude, longitude)
                if weather_data:
                    all_data.update(weather_data)
            except Exception as e:
                log.error(f"Current weather collection failed: {e}")
        
        if self.selected_fields.get('air_quality'):
            try:
                air_data = self.collect_air_quality(latitude, longitude)
                if air_data:
                    all_data.update(air_data)
            except Exception as e:
                log.error(f"Air quality collection failed: {e}")
        
        return all_data

    def _extract_weather_data(self, data):
        """Extract weather data from API response using field mappings."""
        extracted = {}
        
        if not self.config_dict:
            return extracted
        
        service_config = self.config_dict.get('OpenWeatherService', {})
        field_mappings = service_config.get('field_mappings', {})
        current_weather_mappings = field_mappings.get('current_weather', {})
        
        for service_field in self.selected_fields.get('current_weather', []):
            field_mapping = current_weather_mappings.get(service_field, {})
            if not isinstance(field_mapping, dict):
                continue
                
            api_path = field_mapping.get('api_path', '')
            db_field = field_mapping.get('database_field', f'ow_{service_field}')
            
            if api_path:
                try:
                    value = self._extract_value_from_path(data, api_path)
                    if value is not None:
                        extracted[db_field] = value
                except (KeyError, IndexError, TypeError):
                    continue
        
        if extracted:
            extracted['ow_weather_timestamp'] = time.time()
        
        return extracted

    def _extract_air_quality_data(self, data):
        """Extract air quality data from API response using field mappings."""
        extracted = {}
        
        if not self.config_dict:
            return extracted
        
        service_config = self.config_dict.get('OpenWeatherService', {})
        field_mappings = service_config.get('field_mappings', {})
        air_quality_mappings = field_mappings.get('air_quality', {})
        
        for service_field in self.selected_fields.get('air_quality', []):
            field_mapping = air_quality_mappings.get(service_field, {})
            if not isinstance(field_mapping, dict):
                continue
                
            api_path = field_mapping.get('api_path', '')
            db_field = field_mapping.get('database_field', f'ow_{service_field}')
            
            if api_path:
                try:
                    value = self._extract_value_from_path(data, api_path)
                    if value is not None:
                        extracted[db_field] = value
                except (KeyError, IndexError, TypeError):
                    continue
        
        if extracted:
            extracted['ow_air_quality_timestamp'] = time.time()
        
        return extracted

    def _extract_value_from_path(self, data, path):
        """Extract value from API response using dot notation path."""
        parts = path.split('.')
        current = data
        
        for part in parts:
            if '[' in part and ']' in part:
                key = part.split('[')[0]
                index = int(part.split('[')[1].split(']')[0])
                current = current[key][index]
            else:
                current = current[part]
        
        return current


class OpenWeatherBackgroundThread(threading.Thread):
    """Background scheduler for periodic OpenWeather data collection."""
    
    def __init__(self, config, selected_fields, config_dict=None):
        super(OpenWeatherBackgroundThread, self).__init__(name='OpenWeatherBackgroundThread')
        self.daemon = True
        self.config = config
        self.selected_fields = selected_fields
        self.running = True
        
        self.collector = OpenWeatherDataCollector(
            api_key=config['api_key'],
            timeout=int(config.get('timeout', 30)),
            selected_fields=selected_fields,
            config_dict=config_dict
        )
        
        self.data_lock = threading.Lock()
        self.latest_data = {}
        
        station_config = config_dict.get('Station', {})
        self.latitude = float(station_config.get('latitude', 0.0))
        self.longitude = float(station_config.get('longitude', 0.0))
        
        self.intervals = {
            'current_weather': int(config.get('intervals', {}).get('current_weather', 3600)),
            'air_quality': int(config.get('intervals', {}).get('air_quality', 7200))
        }
        
        self.last_collection = {
            'current_weather': 0,
            'air_quality': 0
        }
        
        log.info(f"OpenWeather background thread initialized for location: {self.latitude}, {self.longitude}")
    
    def run(self):
        """Main background thread loop - coordinates data collection."""
        log.info("OpenWeather background thread started")
        
        while self.running:
            try:
                current_time = time.time()
                
                if ('current_weather' in self.selected_fields and 
                    current_time - self.last_collection['current_weather'] >= self.intervals['current_weather']):
                    self._collect_current_weather()
                    self.last_collection['current_weather'] = current_time
                
                if ('air_quality' in self.selected_fields and 
                    current_time - self.last_collection['air_quality'] >= self.intervals['air_quality']):
                    self._collect_air_quality()
                    self.last_collection['air_quality'] = current_time
                
                time.sleep(60)
                
            except Exception as e:
                log.error(f"Error in OpenWeather background thread: {e}")
                time.sleep(300)
    
    def _collect_current_weather(self):
        """Coordinate current weather collection - delegates to collector."""
        try:
            weather_data = self.collector.collect_current_weather(self.latitude, self.longitude)
            
            if weather_data:
                with self.data_lock:
                    self.latest_data.update(weather_data)
                
                log_success = str(self.config.get('log_success', 'false')).lower() in ('true', 'yes', '1')
                if log_success:
                    log.info(f"Collected current weather data: {len(weather_data)} fields")
            
        except OpenWeatherAPIError as e:
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"OpenWeather API error collecting weather data: {e}")
        except Exception as e:
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"Unexpected error collecting weather data: {e}")
    
    def _collect_air_quality(self):
        """Coordinate air quality collection - delegates to collector."""
        try:
            air_quality_data = self.collector.collect_air_quality(self.latitude, self.longitude)
            
            if air_quality_data:
                with self.data_lock:
                    self.latest_data.update(air_quality_data)
                
                log_success = str(self.config.get('log_success', 'false')).lower() in ('true', 'yes', '1')
                if log_success:
                    log.info(f"Collected air quality data: {len(air_quality_data)} fields")
            
        except OpenWeatherAPIError as e:
            log_errors = str(self.config.get('log_errors', 'true')).lower() in ('true', 'yes', '1')
            if log_errors:
                log.error(f"OpenWeather API error collecting air quality data: {e}")
        except Exception as e:
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
        super(OpenWeatherService, self).__init__(engine, config_dict)
        
        log.info(f"OpenWeather service version {VERSION} starting")
        
        self.engine = engine
        self.config_dict = config_dict
        
        # Get OpenWeather configuration
        self.service_config = config_dict.get('OpenWeatherService', {})
        
        if not self._validate_basic_config():
            log.error("OpenWeather service disabled due to configuration issues")
            return
        
        # Load field selection from new config format (written by install.py)
        self.selected_fields = self._load_field_selection_from_config()
        
        if not self.selected_fields:
            log.error("No field selection found - service disabled")
            log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to configure fields")
            return
        
        # Validate and clean field selection
        self.active_fields = self._validate_and_clean_selection()
        
        if not self.active_fields:
            log.error("No usable fields found - all fields have issues")
            log.error("OpenWeather service disabled - no usable fields available")
            log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to fix configuration")
            return

        # Continue with existing initialization logic...
        self._initialize_data_collection()
        self._setup_unit_system()
        
        # Bind to archive events
        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        
        log.info("OpenWeather service initialized successfully")

    def _initialize_data_collection(self):
        """Initialize data collection components - graceful failure."""
        try:
            self.api_client = OpenWeatherDataCollector(
                api_key=self.service_config['api_key'],
                selected_fields=self.active_fields,
                timeout=int(self.service_config.get('timeout', 30)),
                config_dict=self.config_dict
            )
            
            self.background_thread = OpenWeatherBackgroundThread(
                config=self.service_config,
                selected_fields=self.active_fields,
                config_dict=self.config_dict
            )
            
            self.background_thread.start()
            
            log.info("Data collection initialized successfully")
            self.service_enabled = True
            
        except Exception as e:
            log.error(f"Failed to initialize data collection: {e}")
            log.error("OpenWeather data collection disabled")
            self.service_enabled = False

    def _validate_basic_config(self):
        """Basic configuration validation - keep existing logic."""
        if not self.service_config:
            log.error("OpenWeatherService configuration section not found")
            return False
        
        if not self.service_config.get('enable', '').lower() == 'true':
            log.info("OpenWeather service disabled in configuration")
            return False
        
        api_key = self.service_config.get('api_key', '')
        if not api_key or api_key == 'REPLACE_WITH_YOUR_API_KEY':
            log.error("Valid API key not configured")
            log.error("HINT: Run 'weectl extension reconfigure OpenWeather'")
            return False
        
        return True 

    def _load_field_selection_from_config(self):
        """Load field selection from weewx.conf (written by install.py)."""
        field_selection_config = self.service_config.get('field_selection', {})
        
        if not field_selection_config:
            log.error("No field_selection section found in configuration")
            return {}
        
        # FIX: Read the 'selected_fields' subsection, not the entire field_selection section
        selected_fields_config = field_selection_config.get('selected_fields', {})
        
        if not selected_fields_config:
            log.error("No selected_fields found in field_selection configuration")
            return {}
        
        # Read field selections per module (format: 'current_weather': ['temp', 'humidity', 'pressure'])
        selected_fields = {}
        
        for module_name, field_list in selected_fields_config.items():
            if isinstance(field_list, list) and field_list:
                selected_fields[module_name] = field_list
                log.info(f"Loaded {len(field_list)} fields for module '{module_name}'")
            elif isinstance(field_list, str) and field_list:
                # Handle string format (comma-separated) as fallback
                field_list_parsed = [f.strip() for f in field_list.split(',') if f.strip()]
                if field_list_parsed:
                    selected_fields[module_name] = field_list_parsed
                    log.info(f"Loaded {len(field_list_parsed)} fields for module '{module_name}'")
            else:
                log.warning(f"Invalid field configuration for module '{module_name}': {field_list}")
        
        if not selected_fields:
            log.error("No field selections found in configuration")
            return {}
        
        log.info(f"Loaded field selection from configuration: {list(selected_fields.keys())}")
        return selected_fields

    def _load_field_selection(self):
        """Load field selection - try config first, then fallback to old file method."""
        # Try new config format first
        config_selection = self._load_field_selection_from_config()
        if config_selection:
            return config_selection
        
        # Fallback to old file-based method for backward compatibility
        log.warning("No field selection in main config, checking legacy file...")
        
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        try:
            if os.path.exists(selection_file):
                config = configobj.ConfigObj(selection_file)
                field_selection = config.get('field_selection', {})
                selected_fields = field_selection.get('selected_fields', {})
                
                if not selected_fields:
                    log.warning("No field selection found in legacy configuration file")
                    return {}
                
                log.info(f"Loaded legacy field selection from {selection_file}: {list(selected_fields.keys())}")
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
        """Validate field selection and return only usable fields - updated for new config format."""
        
        if not self.selected_fields:
            log.warning("No field selection available - OpenWeather collection disabled")
            return {}
        
        # NEW: Check if we have the new module-based format or old flat format
        if self._is_module_based_format(self.selected_fields):
            return self._validate_module_based_selection()
        else:
            return self._validate_flat_selection()

    def _is_module_based_format(self, selected_fields):
        """Determine if field selection is in module-based format or flat format."""
        if not selected_fields:
            return False
        
        # Check if values are lists (module format) or booleans (flat format)
        for key, value in selected_fields.items():
            if isinstance(value, list):
                return True
            elif isinstance(value, bool) or value in ['true', 'false']:
                return False
        
        # Default to module-based if we can't determine
        return True

    def _validate_module_based_selection(self):
        """Validate module-based field selection (new format from install.py)."""
        field_manager = FieldSelectionManager(config_dict=self.config_dict)
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
                    # Handle specific field list (normal case)
                    total_selected += len(fields)
                    active_module_fields = self._validate_module_fields(module, fields, expected_fields, existing_db_fields, field_manager)
                else:
                    log.warning(f"Invalid field selection format for module '{module}': {fields}")
                    continue
                
                if active_module_fields:
                    active_fields[module] = active_module_fields
            
            # Summary logging
            total_active = self._count_active_fields(active_fields)
            if total_active > 0:
                log.info(f"Field validation complete: {total_active}/{total_selected} fields active")
                if total_active < total_selected:
                    log.warning(f"{total_selected - total_active} fields unavailable - see errors above")
                    log.warning("HINT: Run 'weectl extension reconfigure OpenWeather' to fix field issues")
            else:
                log.error("No usable fields found - all fields have issues")
            
            return active_fields
            
        except Exception as e:
            log.error(f"Field validation failed: {e}")
            return {}

    def _validate_flat_selection(self):
        """Validate flat field selection (legacy format) - convert to module format."""
        log.info("Converting flat field selection to module format")
        
        # Convert flat format to module format for compatibility
        field_manager = FieldSelectionManager(config_dict=self.config_dict)
        module_fields = {}
        
        try:
            for field_name, selected in self.selected_fields.items():
                if not selected:
                    continue
                
                # Determine which module this field belongs to based on field name
                if field_name.startswith('ow_'):
                    # Map database field name back to service field name
                    service_field = self._map_database_to_service_field(field_name)
                    if not service_field:
                        log.warning(f"Unknown field mapping for {field_name}")
                        continue
                    
                    # Determine module based on field characteristics
                    module = self._determine_module_for_field(field_name)
                    if not module:
                        log.warning(f"Cannot determine module for field {field_name}")
                        continue
                    
                    if module not in module_fields:
                        module_fields[module] = []
                    module_fields[module].append(service_field)
            
            if module_fields:
                log.info(f"Converted flat selection to modules: {list(module_fields.keys())}")
                # Validate the converted module format
                self.selected_fields = module_fields
                return self._validate_module_based_selection()
            else:
                log.error("No valid fields found in flat selection")
                return {}
                
        except Exception as e:
            log.error(f"Failed to convert flat field selection: {e}")
            return {}

    def _determine_module_for_field(self, field_name):
        """Determine which module a field belongs to based on field name."""
        if any(pollutant in field_name for pollutant in ['pm25', 'pm10', 'aqi', 'ozone', 'no2', 'so2', 'co']):
            return 'air_quality'
        elif any(weather in field_name for weather in ['temp', 'humidity', 'pressure', 'wind', 'cloud', 'rain', 'snow', 'weather']):
            return 'current_weather'
        else:
            return 'current_weather'  # Default
        
    def _validate_module_fields(self, module, fields, expected_fields, existing_db_fields, field_manager):
        """Validate fields for a specific module - fails when configuration is missing."""
        active_fields = []
        
        if not fields:
            return active_fields
        
        field_list = fields if isinstance(fields, list) else []
        
        for field in field_list:
            try:
                # Find the database field name for this logical field
                db_field = self._get_database_field_name(module, field, field_manager)
                
                if db_field is None:
                    log.error(f"Cannot map field '{field}' in module '{module}' - configuration missing")
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
        """Get database field name for a logical field name using CONF data."""
        try:
            db_field = field_manager._map_service_to_database_field(field, module)
            if db_field is None:
                log.error(f"Failed to map {module}.{field} - no configuration data")
            return db_field
        except Exception as e:
            log.error(f"Error looking up database field for {module}.{field}: {e}")
            return None

    def _setup_unit_system(self):
        """Set up WeeWX unit system integration and detect unit preferences."""
        try:
            import weewx.units
            
            # Detect WeeWX unit system from configuration
            weewx_unit_system = self._detect_weewx_unit_system()
            
            # Map to OpenWeather API units parameter
            self.api_units = self._map_to_openweather_units(weewx_unit_system)
            
            log.info(f"Unit system: WeeWX='{weewx_unit_system}' → OpenWeather='{self.api_units}'")
            
            # Add concentration unit group for air quality if not exists
            if 'group_concentration' not in weewx.units.USUnits:
                weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
            
            # Add unit mappings for all collected fields
            for module_name, field_list in self.active_fields.items():
                for service_field in field_list:
                    # Map service field to database field
                    db_field = self._get_database_field_name(module_name, service_field, self.field_manager)
                    if not db_field:
                        continue
                    
                    # Map to appropriate unit groups based on field content
                    if any(temp_word in db_field.lower() for temp_word in ['temperature', 'temp', 'feels']):
                        weewx.units.obs_group_dict[db_field] = 'group_temperature'
                    elif 'humidity' in db_field.lower():
                        weewx.units.obs_group_dict[db_field] = 'group_percent'
                    elif 'pressure' in db_field.lower():
                        weewx.units.obs_group_dict[db_field] = 'group_pressure'
                    elif 'wind' in db_field.lower():
                        if any(dir_word in db_field.lower() for dir_word in ['direction', 'deg', 'dir']):
                            weewx.units.obs_group_dict[db_field] = 'group_direction'
                        else:
                            weewx.units.obs_group_dict[db_field] = 'group_speed'
                    elif any(pollutant in db_field.lower() for pollutant in ['pm25', 'pm10', 'ozone', 'no2', 'so2', 'co']):
                        weewx.units.obs_group_dict[db_field] = 'group_concentration'
                    elif 'aqi' in db_field.lower():
                        weewx.units.obs_group_dict[db_field] = 'group_count'
                    elif 'visibility' in db_field.lower():
                        weewx.units.obs_group_dict[db_field] = 'group_distance'
                    elif 'cloud' in db_field.lower():
                        weewx.units.obs_group_dict[db_field] = 'group_percent'
                    elif any(precip_word in db_field.lower() for precip_word in ['rain', 'snow']):
                        weewx.units.obs_group_dict[db_field] = 'group_rain'
                    else:
                        weewx.units.obs_group_dict[db_field] = 'group_count'
            
            # Add formatting for concentration
            if 'microgram_per_meter_cubed' not in weewx.units.default_unit_format_dict:
                weewx.units.default_unit_format_dict['microgram_per_meter_cubed'] = '%.1f'
            
            if 'microgram_per_meter_cubed' not in weewx.units.default_unit_label_dict:
                weewx.units.default_unit_label_dict['microgram_per_meter_cubed'] = ' μg/m³'
            
            log.info("Unit system configured for OpenWeather fields")
            
        except Exception as e:
            log.error(f"Failed to setup unit system: {e}")

    def _detect_weewx_unit_system(self):
        """Detect WeeWX unit system from configuration."""
        try:
            # Look for StdConvert target_unit in configuration
            stdconvert_config = self.config.get('StdConvert', {})
            target_unit = stdconvert_config.get('target_unit', 'US').upper()
            
            if target_unit in ['US', 'METRICWX', 'METRIC']:
                return target_unit
            else:
                log.warning(f"Unknown WeeWX unit system '{target_unit}', defaulting to US")
                return 'US'
                
        except Exception as e:
            log.warning(f"Could not detect WeeWX unit system: {e}, defaulting to US")
            return 'US'

    def _map_to_openweather_units(self, weewx_unit_system):
        """Map WeeWX unit system to OpenWeather API units parameter."""
        mapping = {
            'US': 'imperial',        # F, mph, inHg
            'METRICWX': 'metric',    # C, m/s, mbar  
            'METRIC': 'metric'       # C, km/hr -> m/s (needs conversion), mbar
        }
        
        api_units = mapping.get(weewx_unit_system, 'metric')  # Fallback to metric (not Kelvin!)
        
        # Store conversion needed flag for METRIC system
        self.needs_wind_conversion = (weewx_unit_system == 'METRIC')
        
        return api_units

    def _get_all_fields_for_module(self, module):
        """Get all available fields for a module from service configuration."""
        try:
            field_mappings = self.service_config.get('field_mappings', {})
            module_mappings = field_mappings.get(module, {})
            return list(module_mappings.keys())
        except Exception as e:
            log.error(f"Error getting fields for module '{module}': {e}")
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
    
    def new_archive_record(self, event):
        """Inject OpenWeather data into archive record with unit conversion - never fails."""
        if not self.service_enabled:
            return  # Silently skip if service is disabled
        
        try:
            # Get latest collected data
            collected_data = self.get_latest_data()
            
            if not collected_data:
                return  # No data available
            
            # Build record with all expected fields, using None for missing data
            record_update = {}
            
            # Use existing field manager with config
            field_manager = FieldSelectionManager(self.config_dict)
            expected_fields = field_manager.get_database_field_mappings(self.active_fields)
            
            fields_injected = 0
            for db_field, field_type in expected_fields.items():
                if db_field in collected_data and collected_data[db_field] is not None:
                    # Successfully collected data - apply conversion if needed
                    raw_value = collected_data[db_field]
                    
                    # Determine service field and module for conversion
                    service_field = db_field.replace('ow_', '')  # e.g., 'ow_wind_speed' → 'wind_speed'
                    module_name = self._determine_module_for_field(db_field)
                    
                    # Apply unit conversion if needed
                    converted_value = self._convert_field_if_needed(service_field, raw_value, module_name)
                    
                    record_update[db_field] = converted_value
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

    def get_latest_data(self):
        """Get latest collected data - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                return self.background_thread.get_latest_data()
        except Exception as e:
            log.error(f"Error getting latest data: {e}")
        return {}
    
    def _setup_unit_system(self):
        """Set up unit system for OpenWeather fields using ONLY conf data."""
        try:
            import weewx.units
            
            # Get unit system info from conf (written by install.py)
            unit_config = self.service_config.get('unit_system', {})
            weewx_unit_system = unit_config.get('weewx_system', 'US')
            api_units = unit_config.get('api_units', 'imperial')
            
            log.info(f"Unit system: WeeWX='{weewx_unit_system}' → OpenWeather='{api_units}'")
            
            # Add concentration unit group for air quality
            if 'group_concentration' not in weewx.units.USUnits:
                weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
            
            # ONLY read unit groups from conf - NO hardcoding or determination
            conf_field_mappings = self.service_config.get('field_mappings', {})
            
            for module_name, field_list in self.active_fields.items():
                module_mappings = conf_field_mappings.get(module_name, {})
                
                for service_field in field_list:
                    field_mapping = module_mappings.get(service_field, {})
                    
                    if isinstance(field_mapping, dict):
                        db_field = field_mapping.get('database_field', f'ow_{service_field}')
                        unit_group = field_mapping.get('unit_group', 'group_count')
                        
                        # Assign unit group from conf data ONLY
                        weewx.units.obs_group_dict[db_field] = unit_group
            
            log.info("Unit system setup completed")
            
        except Exception as e:
            log.error(f"Failed to setup unit system: {e}")

    def _get_api_units_parameter(self):
        """Get the units parameter for OpenWeather API calls (metric/imperial/standard)."""
        try:
            unit_config = self.service_config.get('unit_system', {})
            api_units = unit_config.get('api_units', 'metric')
            return api_units
        except Exception as e:
            log.error(f"Error getting API units parameter: {e}")
            return 'metric'  # Safe fallback

    def _convert_field_if_needed(self, field_name, value, module_name):
        """Generic field conversion based on CONF data from YAML (replaces hardcoded wind speed method)."""
        try:
            if value is None:
                return value
            
            # Get field mapping for this specific field
            field_mappings = self.service_config.get('field_mappings', {})
            module_mappings = field_mappings.get(module_name, {})
            field_config = module_mappings.get(field_name, {})
            
            # Check if this field needs conversion
            conversion_name = field_config.get('unit_conversion')
            if not conversion_name or conversion_name == 'None':
                return value  # No conversion needed - don't log warning
            
            # Get conversion specifications (written by install.py from YAML)
            unit_conversions = self.service_config.get('unit_conversions', {})
            conversion_spec = unit_conversions.get(conversion_name, {})
            
            if not conversion_spec:
                log.warning(f"Conversion '{conversion_name}' not found for field {field_name}")
                return value
            
            # Check if conversion applies to current unit system
            applies_when = conversion_spec.get('applies_when', {})
            unit_system_config = self.service_config.get('unit_system', {})
            
            current_weewx_system = unit_system_config.get('weewx_system')
            current_api_units = unit_system_config.get('api_units')
            
            required_weewx = applies_when.get('weewx_system')
            required_api = applies_when.get('openweather_units')
            
            # Only convert if conditions match
            if (required_weewx and current_weewx_system != required_weewx) or \
            (required_api and current_api_units != required_api):
                return value  # Conditions don't match, no conversion
            
            # Apply the conversion formula
            formula = conversion_spec.get('formula', 'x')
            try:
                # Simple formula evaluation (e.g., "x * 3.6")
                # Replace 'x' with the actual value
                converted_value = eval(formula.replace('x', str(float(value))))
                
                log.debug(f"Converted {field_name}: {value} → {converted_value} "
                        f"({conversion_spec.get('from_unit', '?')} → {conversion_spec.get('to_unit', '?')})")
                
                return converted_value
                
            except Exception as eval_error:
                log.error(f"Error evaluating conversion formula '{formula}' for {field_name}: {eval_error}")
                return value
            
        except Exception as e:
            log.error(f"Error converting field {field_name}: {e}")
            return value
            
    def shutDown(self):
        """Clean shutdown - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                self.background_thread.stop()
                log.info("OpenWeather service shutdown complete")
        except Exception as e:
            log.error(f"Error during OpenWeather shutdown: {e}")

            
class OpenWeatherTester:
    """Simple installation verification for the OpenWeather extension."""
    
    def __init__(self):
        self.latitude = None
        self.longitude = None
        self.api_key = None  # Will be loaded from service config
        
        print(f"OpenWeather Extension Tester v{VERSION}")
        print("=" * 60)
        
        # Initialize required data structures
        self.config_dict = None
        self.service_config = None
        self.field_manager = None
        
        # Load real WeeWX configuration
        self._load_weewx_config()
        
        # Initialize field manager and get station coordinates if config is available
        if self.config_dict:
            self.field_manager = FieldSelectionManager(config_dict=self.config_dict)
            self.service_config = self.config_dict.get('OpenWeatherService', {})
            # Get API key from service configuration
            self.api_key = self.service_config.get('api_key', '')
            
            # Get station coordinates from WeeWX configuration
            station_config = self.config_dict.get('Station', {})
            self.latitude = float(station_config.get('latitude', 0.0))
            self.longitude = float(station_config.get('longitude', 0.0))
            
            if self.latitude != 0.0 and self.longitude != 0.0:
                print(f"Testing location: {self.latitude}, {self.longitude}")
            else:
                print("⚠️ No station coordinates configured")
        else:
            print("⚠️ No WeeWX configuration loaded")
        
    def _load_weewx_config(self):
        """Load the actual WeeWX configuration."""
        config_paths = [
            '/etc/weewx/weewx.conf',
            '/home/weewx/weewx.conf',
            '/opt/weewx/weewx.conf',
            os.path.expanduser('~/weewx-data/weewx.conf')
        ]
        
        for config_path in config_paths:
            if os.path.exists(config_path):
                try:
                    import configobj
                    self.config_dict = configobj.ConfigObj(config_path)
                    print(f"✓ Loaded WeeWX configuration: {config_path}")
                    return
                except Exception as e:
                    print(f"❌ Error loading {config_path}: {e}")
                    continue
        
        print("❌ No WeeWX configuration found - extension may not be installed")
    
    def test_installation(self):
        """Test if extension is properly installed."""
        print("\n🔧 TESTING INSTALLATION")
        print("-" * 40)
        
        if not self.config_dict:
            print("❌ No WeeWX configuration available")
            return False
        
        success = True
        
        # Check service registration
        print("Checking service registration...")
        try:
            engine_config = self.config_dict.get('Engine', {})
            services_config = engine_config.get('Services', {})
            data_services = services_config.get('data_services', '')
            
            if isinstance(data_services, list):
                data_services = ', '.join(data_services)
            
            if 'user.openweather.OpenWeatherService' in data_services:
                print("  ✓ Service registered in WeeWX configuration")
            else:
                print("  ❌ Service not registered in data_services")
                success = False
        except Exception as e:
            print(f"  ❌ Error checking service registration: {e}")
            success = False
        
        # Check OpenWeatherService configuration
        print("Checking service configuration...")
        if self.service_config:
            print("  ✓ OpenWeatherService section found")
            
            # Check API key
            api_key = self.service_config.get('api_key', '')
            if api_key and api_key != 'REPLACE_WITH_YOUR_API_KEY':
                print(f"  ✓ API key configured: {api_key[:8]}***")
            else:
                print("  ❌ No valid API key configured")
                success = False
        else:
            print("  ❌ No OpenWeatherService configuration found")
            success = False
        
        # Check station coordinates - REQUIRED for API calls
        print("Checking station coordinates...")
        if self.latitude is not None and self.longitude is not None:
            if self.latitude != 0.0 and self.longitude != 0.0:
                print(f"  ✓ Station coordinates configured: {self.latitude}, {self.longitude}")
            else:
                print("  ❌ Station coordinates are zero - invalid location")
                success = False
        else:
            print("  ❌ No station coordinates found in configuration")
            success = False
        
        # Check field selection configuration
        print("Checking field selection...")
        try:
            field_selection = self.service_config.get('field_selection', {})
            selected_fields = field_selection.get('selected_fields', {})
            
            if selected_fields:
                field_count = sum(len(fields) if isinstance(fields, list) else 0 
                                for fields in selected_fields.values())
                print(f"  ✓ Field selection configured: {field_count} fields selected")
            else:
                print("  ❌ No field selection configuration found")
                success = False
        except Exception as e:
            print(f"  ❌ Error checking field selection: {e}")
            success = False
        
        # Check database fields
        print("Checking database fields...")
        try:
            db_fields = self._get_database_fields()
            ow_fields = [f for f in db_fields if f.startswith('ow_')]
            
            if ow_fields:
                print(f"  ✓ Found {len(ow_fields)} OpenWeather database fields")
            else:
                print("  ❌ No OpenWeather fields found in database")
                success = False
        except Exception as e:
            print(f"  ❌ Error checking database fields: {e}")
            success = False
        
        return success
    
    def test_api_connectivity(self):
        """Test API connectivity using configured API key."""
        print("\n🌐 TESTING API CONNECTIVITY")
        print("-" * 40)
        
        # Check prerequisites first
        if not self.api_key or self.api_key == 'REPLACE_WITH_YOUR_API_KEY':
            print("❌ No valid API key configured in service - cannot test API")
            return False
        
        if not self.latitude or not self.longitude or (self.latitude == 0.0 and self.longitude == 0.0):
            print("❌ No valid station coordinates - cannot test API")
            return False
        
        success = True
        
        # Test current weather API
        print("Testing current weather API...")
        try:
            collector = OpenWeatherDataCollector(
                self.api_key, 
                timeout=30,
                selected_fields={'current_weather': ['temp']},
                config_dict=self.config_dict
            )
            weather_data = collector.collect_current_weather(self.latitude, self.longitude)
            
            if weather_data and 'ow_temperature' in weather_data:
                print(f"  ✓ Weather API working: {weather_data['ow_temperature']:.1f}°C")
            else:
                print("  ❌ Weather API: No temperature data received")
                success = False
        except OpenWeatherAPIError as e:
            print(f"  ❌ Weather API error: {e}")
            success = False
        except Exception as e:
            print(f"  ❌ Weather API unexpected error: {e}")
            success = False
        
        # Test air quality API
        print("Testing air quality API...")
        try:
            collector = OpenWeatherDataCollector(
                self.api_key,
                timeout=30,
                selected_fields={'air_quality': ['aqi']},
                config_dict=self.config_dict
            )
            air_data = collector.collect_air_quality(self.latitude, self.longitude)
            
            if air_data and 'ow_aqi' in air_data:
                print(f"  ✓ Air quality API working: AQI {air_data['ow_aqi']}")
            else:
                print("  ❌ Air quality API: No AQI data received")
                success = False
        except OpenWeatherAPIError as e:
            print(f"  ❌ Air quality API error: {e}")
            success = False
        except Exception as e:
            print(f"  ❌ Air quality API unexpected error: {e}")
            success = False
        
        return success
    
    def _get_database_fields(self):
        """Get list of database fields."""
        if not self.config_dict:
            return []
        
        try:
            db_binding = 'wx_binding'
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    fields.append(column[1])
                return fields
        except Exception as e:
            raise Exception(f"Database access failed: {e}")
    
    def run_basic_tests(self):
        """Run essential installation verification tests."""
        print(f"\n🧪 RUNNING BASIC INSTALLATION TESTS")
        print("=" * 60)
        print(f"OpenWeather Extension v{VERSION}")
        print("=" * 60)
        
        tests_passed = 0
        total_tests = 0
        
        # Test installation
        total_tests += 1
        if self.test_installation():
            tests_passed += 1
            print("\nInstallation Test: ✅ PASSED")
        else:
            print("\nInstallation Test: ❌ FAILED")
        
        # Test API if service is properly configured
        if self.api_key and self.api_key != 'REPLACE_WITH_YOUR_API_KEY':
            total_tests += 1
            if self.test_api_connectivity():
                tests_passed += 1
                print("\nAPI Connectivity Test: ✅ PASSED")
            else:
                print("\nAPI Connectivity Test: ❌ FAILED")
        else:
            print("\nAPI Connectivity Test: ⚠️ SKIPPED (no valid API key configured)")
        
        # Summary
        print("\n" + "=" * 60)
        print(f"BASIC TEST SUMMARY: {tests_passed}/{total_tests} tests passed")
        
        if tests_passed == total_tests:
            print("🎉 ALL BASIC TESTS PASSED!")
            print("Extension is properly installed and ready to use.")
        else:
            print("❌ SOME TESTS FAILED")
            print("Check the output above for specific issues.")
        
        return tests_passed == total_tests


def main():
    """Main function for command-line testing."""
    parser = argparse.ArgumentParser(
        description='OpenWeather Extension Basic Testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test installation only
  python3 openweather.py --test-install
  
  # Test everything (uses service configuration)
  python3 openweather.py --test-all
        """
    )
    
    # Simple test options only
    parser.add_argument('--test-install', action='store_true',
                       help='Test installation (database + service registration)')
    parser.add_argument('--test-api', action='store_true', 
                       help='Test API connectivity (uses configured API key)')
    parser.add_argument('--test-all', action='store_true',
                       help='Run all basic tests')
    
    args = parser.parse_args()
    
    # Initialize simple tester (uses all service configuration)
    tester = OpenWeatherTester()
    
    # Run requested tests
    if args.test_all:
        success = tester.run_basic_tests()
    elif args.test_install:
        success = tester.test_installation()
    elif args.test_api:
        success = tester.test_api_connectivity()
    else:
        print("No tests specified. Use --help to see available options.")
        print("\nQuick options:")
        print("  --test-all       # Test installation + API")
        print("  --test-install   # Test installation only")
        print("  --test-api       # Test API connectivity")
        return
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()

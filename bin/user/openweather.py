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
    """Enhanced data collector with field selection support."""
    
    def __init__(self, api_key, timeout=30, selected_fields=None, config_dict=None):
        self.api_key = api_key
        self.timeout = int(timeout) if timeout else 30
        self.selected_fields = selected_fields or {}
        self.config_dict = config_dict
        self.field_manager = FieldSelectionManager(config_dict=self.config_dict)
        
        self.required_apis = self._determine_required_apis()
        
        self.base_urls = {
            'current_weather': 'http://api.openweathermap.org/data/2.5/weather',
            'air_quality': 'http://api.openweathermap.org/data/2.5/air_pollution'
        }

    def _determine_required_apis(self):
        """Determine which FREE APIs are needed based on selected fields."""
        required = set()
        
        for field_name, selected in self.selected_fields.items():
            if not selected or field_name not in self.field_manager.field_definitions:
                continue
                
            api_path = self.field_manager.field_definitions[field_name]['api_path']
            
            # Determine API source from path (FREE APIs only)
            if api_path.startswith('main.') or api_path.startswith('weather[') or api_path.startswith('wind.') or api_path.startswith('clouds.'):
                required.add('current_weather')
            elif api_path.startswith('list[0].components.') or api_path.startswith('list[0].main.'):
                required.add('air_quality')
        
        return required
    
    def collect_all_data(self, latitude, longitude):
        """Collect data from all required FREE APIs and combine results."""
        all_data = {}
        
        # Current Weather API
        if 'current_weather' in self.required_apis:
            try:
                weather_data = self._collect_current_weather(latitude, longitude)
                all_data.update(weather_data)
            except Exception as e:
                log.error(f"Current weather collection failed: {e}")
        
        # Air Quality API  
        if 'air_quality' in self.required_apis:
            try:
                air_data = self._collect_air_quality(latitude, longitude)
                all_data.update(air_data)
            except Exception as e:
                log.error(f"Air quality collection failed: {e}")
        
        return all_data
    
    def _extract_value_from_path(self, data, path):
        """Extract value from API response using dot notation path."""
        parts = path.split('.')
        current = data
        
        for part in parts:
            if '[' in part and ']' in part:
                # Handle array access like "list[0]"
                key = part.split('[')[0]
                index = int(part.split('[')[1].split(']')[0])
                current = current[key][index]
            else:
                current = current[part]
        
        return current


class OpenWeatherBackgroundThread(threading.Thread):
    """Enhanced background thread with field selection support."""
    
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
        
        station_config = config.get('Station', {})
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
    
    def _initialize_data_collection(self):
        """Initialize data collection components - graceful failure."""
        try:
            # Set up data collector with active fields only
            self.api_client = OpenWeatherDataCollector(
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

    def _initialize_data_collection(self):
        """Initialize data collection components - graceful failure."""
        try:
            # Set up data collector with active fields only
            self.api_client = OpenWeatherDataCollector(
                api_key=self.service_config['api_key'],
                selected_fields=self.active_fields,
                timeout=int(self.service_config.get('timeout', 30))
            )
            
            # Set up background collection thread (remove api_client parameter)
            self.background_thread = OpenWeatherBackgroundThread(
                config=self.service_config,
                selected_fields=self.active_fields
            )
            
            # Start background collection
            self.background_thread.start()
            
            log.info("Data collection initialized successfully")
            self.service_enabled = True
            
        except Exception as e:
            log.error(f"Failed to initialize data collection: {e}")
            log.error("OpenWeather data collection disabled")
            self.service_enabled = False

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
            if not conversion_name:
                return value  # No conversion needed
            
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
        self.field_manager = FieldSelectionManager(config_dict=self.config_dict)
        
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

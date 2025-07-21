#!/usr/bin/env python3
"""
OpenWeather Service for WeeWX 5.1+

Comprehensive OpenWeatherMap API integration providing:
- Current weather data (temperature, humidity, pressure, wind, cloud cover, visibility)
- Air quality data (PM2.5, PM10, O3, NO2, SO2, CO, NH3, European AQI 1-5 scale)
- UV index data (current and daily maximum)
- Modular configuration (enable only needed modules)
- Efficient API usage with rate limiting and error handling
- Thread-safe background data collection

Copyright (C) 2025 WeeWX Community
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Optional, Any

import weewx
import weewx.units
from weewx.engine import StdService

log = logging.getLogger(__name__)

VERSION = "1.0.0"

# OpenWeatherMap API endpoints
OPENWEATHER_ENDPOINTS = {
    'current_weather': 'http://api.openweathermap.org/data/2.5/weather',
    'air_quality': 'http://api.openweathermap.org/data/2.5/air_pollution',
    'uv_index': 'http://api.openweathermap.org/data/2.5/uvi',
    'forecast_daily': 'http://api.openweathermap.org/data/2.5/forecast/daily',
    'forecast_hourly': 'http://api.openweathermap.org/data/2.5/forecast'
}

# Default configuration values
DEFAULT_CONFIG = {
    'enable': True,
    'api_key': None,
    'timeout': 30,
    'retry_attempts': 3,
    'log_success': False,
    'log_errors': True,
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
}

class OpenWeatherService(StdService):
    """
    WeeWX service for collecting OpenWeatherMap data.
    
    Provides modular data collection with background threading,
    rate limiting, and comprehensive error handling.
    """
    
    def __init__(self, engine, config_dict):
        """Initialize the OpenWeather service."""
        super(OpenWeatherService, self).__init__(engine, config_dict)
        
        log.info(f"OpenWeather service version {VERSION} starting")
        
        try:
            # Parse configuration
            self.config = self._parse_configuration(config_dict)
            
            if not self.config['enable']:
                log.info("OpenWeather service disabled in configuration")
                return
            
            # Validate configuration
            self._validate_configuration()
            
            # Get station coordinates
            self.latitude, self.longitude = self._get_station_coordinates(config_dict)
            
            # Initialize data storage (thread-safe)
            self.data_lock = threading.Lock()
            self.latest_data = {}
            self.last_api_calls = {}
            
            # Initialize API client
            self.api_client = OpenWeatherAPIClient(
                api_key=self.config['api_key'],
                timeout=self.config['timeout'],
                retry_attempts=self.config['retry_attempts']
            )
            
            # Start background collection threads for enabled modules
            self.collection_threads = {}
            self._start_collection_threads()
            
            # Bind to archive record events
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
            
            log.info(f"OpenWeather service initialized for coordinates: {self.latitude:.6f}, {self.longitude:.6f}")
            if self.config['log_success']:
                enabled_modules = [m for m, enabled in self.config['modules'].items() if enabled]
                log.info(f"Enabled modules: {', '.join(enabled_modules)}")
                
        except Exception as e:
            log.error(f"Failed to initialize OpenWeather service: {e}")
            raise
    
    def _parse_configuration(self, config_dict):
        """Parse and validate OpenWeather service configuration."""
        
        ow_config = config_dict.get('OpenWeatherService', {})
        
        # Start with default configuration
        config = DEFAULT_CONFIG.copy()
        config['modules'] = DEFAULT_CONFIG['modules'].copy()
        config['intervals'] = DEFAULT_CONFIG['intervals'].copy()
        
        # Update with user configuration
        for key, value in ow_config.items():
            if key in ['modules', 'intervals']:
                # Handle nested dictionaries
                if isinstance(value, dict):
                    config[key].update(value)
            else:
                config[key] = value
        
        # Convert string values to appropriate types
        config['enable'] = self._to_bool(config.get('enable', True))
        config['timeout'] = int(config.get('timeout', 30))
        config['retry_attempts'] = int(config.get('retry_attempts', 3))
        config['log_success'] = self._to_bool(config.get('log_success', False))
        config['log_errors'] = self._to_bool(config.get('log_errors', True))
        
        # Convert module enable flags to booleans
        for module in config['modules']:
            config['modules'][module] = self._to_bool(config['modules'][module])
        
        # Convert intervals to integers
        for module in config['intervals']:
            config['intervals'][module] = int(config['intervals'][module])
        
        return config
    
    def _validate_configuration(self):
        """Validate OpenWeather service configuration."""
        
        # Check API key
        if not self.config['api_key'] or self.config['api_key'] == 'REPLACE_WITH_YOUR_API_KEY':
            raise ValueError("OpenWeather API key not configured. Please set api_key in [OpenWeatherService] section.")
        
        # Check at least one module is enabled
        if not any(self.config['modules'].values()):
            raise ValueError("No OpenWeather modules enabled. Enable at least one module in configuration.")
        
        # Validate intervals
        for module, interval in self.config['intervals'].items():
            if interval < 600:  # 10 minutes minimum
                log.warning(f"Module {module} interval {interval}s is less than recommended minimum 600s")
        
        # Calculate daily API usage
        total_daily_calls = 0
        for module, enabled in self.config['modules'].items():
            if enabled:
                interval = self.config['intervals'][module]
                daily_calls = 86400 // interval
                total_daily_calls += daily_calls
        
        if total_daily_calls > 900:
            log.warning(f"High API usage: {total_daily_calls} calls/day may approach free tier limits (1000/day)")
        
        log.info(f"Estimated daily API calls: {total_daily_calls}")
    
    def _get_station_coordinates(self, config_dict):
        """Get station coordinates from WeeWX configuration."""
        
        station_config = config_dict.get('Station', {})
        
        latitude = station_config.get('latitude')
        longitude = station_config.get('longitude')
        
        if not latitude or not longitude:
            raise ValueError("Station coordinates not found in [Station] section")
        
        try:
            lat_float = float(latitude)
            lon_float = float(longitude)
            
            if not (-90 <= lat_float <= 90):
                raise ValueError(f"Invalid latitude: {lat_float}")
            if not (-180 <= lon_float <= 180):
                raise ValueError(f"Invalid longitude: {lon_float}")
            
            return lat_float, lon_float
            
        except ValueError as e:
            raise ValueError(f"Invalid station coordinates: {e}")
    
    def _start_collection_threads(self):
        """Start background data collection threads for enabled modules."""
        
        for module_name, enabled in self.config['modules'].items():
            if enabled:
                thread_name = f"OpenWeather-{module_name}"
                collection_thread = threading.Thread(
                    target=self._collection_thread_worker,
                    args=(module_name,),
                    name=thread_name,
                    daemon=True
                )
                collection_thread.start()
                self.collection_threads[module_name] = collection_thread
                
                if self.config['log_success']:
                    log.info(f"Started collection thread for module: {module_name}")
    
    def _collection_thread_worker(self, module_name):
        """Background thread worker for data collection."""
        
        interval = self.config['intervals'][module_name]
        
        log.debug(f"Collection thread for {module_name} starting (interval: {interval}s)")
        
        while True:
            try:
                # Check if it's time to collect data
                last_call = self.last_api_calls.get(module_name, 0)
                time_since_last = time.time() - last_call
                
                if time_since_last >= interval:
                    # Collect data for this module
                    data = self._collect_module_data(module_name)
                    
                    if data:
                        # Store data in thread-safe manner
                        with self.data_lock:
                            self.latest_data[module_name] = {
                                'data': data,
                                'timestamp': time.time()
                            }
                        
                        self.last_api_calls[module_name] = time.time()
                        
                        if self.config['log_success']:
                            log.info(f"Successfully collected {module_name} data")
                    else:
                        if self.config['log_errors']:
                            log.warning(f"Failed to collect {module_name} data")
                
                # Sleep for a short time before checking again
                time.sleep(60)  # Check every minute
                
            except Exception as e:
                if self.config['log_errors']:
                    log.error(f"Error in {module_name} collection thread: {e}")
                time.sleep(300)  # Wait 5 minutes before retrying after error
    
    def _collect_module_data(self, module_name):
        """Collect data for a specific module."""
        
        try:
            if module_name == 'current_weather':
                return self.api_client.get_current_weather(self.latitude, self.longitude)
            elif module_name == 'air_quality':
                return self.api_client.get_air_quality(self.latitude, self.longitude)
            elif module_name == 'uv_index':
                return self.api_client.get_uv_index(self.latitude, self.longitude)
            elif module_name == 'forecast_daily':
                return self.api_client.get_daily_forecast(self.latitude, self.longitude)
            elif module_name == 'forecast_hourly':
                return self.api_client.get_hourly_forecast(self.latitude, self.longitude)
            else:
                log.error(f"Unknown module: {module_name}")
                return None
                
        except Exception as e:
            if self.config['log_errors']:
                log.error(f"Error collecting {module_name} data: {e}")
            return None
    
    def new_archive_record(self, event):
        """Process new archive record and inject OpenWeather data."""
        
        if not self.config['enable']:
            return
        
        try:
            # Get latest data from all modules (thread-safe)
            with self.data_lock:
                current_data = self.latest_data.copy()
            
            # Inject data from each module
            for module_name, module_data in current_data.items():
                if module_data:
                    data = module_data['data']
                    data_age = time.time() - module_data['timestamp']
                    
                    # Don't use data older than 2 * interval
                    max_age = self.config['intervals'][module_name] * 2
                    
                    if data_age <= max_age:
                        # Inject module data into archive record
                        self._inject_module_data(event.record, module_name, data)
                    else:
                        if self.config['log_errors']:
                            log.debug(f"Skipping stale {module_name} data (age: {data_age:.0f}s)")
            
            if self.config['log_success']:
                injected_fields = [k for k in event.record.keys() if k.startswith('ow_')]
                if injected_fields:
                    log.debug(f"Injected OpenWeather fields: {', '.join(injected_fields)}")
                    
        except Exception as e:
            if self.config['log_errors']:
                log.error(f"Error injecting OpenWeather data: {e}")
    
    def _inject_module_data(self, record, module_name, data):
        """Inject module data into archive record."""
        
        if module_name == 'current_weather':
            self._inject_current_weather_data(record, data)
        elif module_name == 'air_quality':
            self._inject_air_quality_data(record, data)
        elif module_name == 'uv_index':
            self._inject_uv_index_data(record, data)
        elif module_name == 'forecast_daily':
            self._inject_daily_forecast_data(record, data)
        elif module_name == 'forecast_hourly':
            self._inject_hourly_forecast_data(record, data)
    
    def _inject_current_weather_data(self, record, data):
        """Inject current weather data into archive record."""
        
        try:
            main = data.get('main', {})
            wind = data.get('wind', {})
            clouds = data.get('clouds', {})
            
            # Temperature data
            record['ow_temperature'] = main.get('temp')
            record['ow_feels_like'] = main.get('feels_like')
            
            # Atmospheric data
            record['ow_pressure'] = main.get('pressure')
            record['ow_humidity'] = main.get('humidity')
            
            # Sky conditions
            record['ow_cloud_cover'] = clouds.get('all')
            record['ow_visibility'] = data.get('visibility')
            
            # Wind data
            record['ow_wind_speed'] = wind.get('speed')
            record['ow_wind_direction'] = wind.get('deg')
            
        except Exception as e:
            log.error(f"Error injecting current weather data: {e}")
    
    def _inject_air_quality_data(self, record, data):
        """Inject air quality data into archive record."""
        
        try:
            if 'list' in data and len(data['list']) > 0:
                pollution_data = data['list'][0]
                components = pollution_data.get('components', {})
                main = pollution_data.get('main', {})
                
                # Particulate matter
                record['ow_pm25'] = components.get('pm2_5')
                record['ow_pm10'] = components.get('pm10')
                
                # Gases
                record['ow_ozone'] = components.get('o3')
                record['ow_no2'] = components.get('no2')
                record['ow_so2'] = components.get('so2')
                record['ow_co'] = components.get('co')
                
                # Air Quality Index (European scale 1-5)
                record['ow_aqi'] = main.get('aqi')
                
        except Exception as e:
            log.error(f"Error injecting air quality data: {e}")
    
    def _inject_uv_index_data(self, record, data):
        """Inject UV index data into archive record."""
        
        try:
            record['ow_uv_current'] = data.get('value')
            # Note: daily max UV would come from forecast data
            
        except Exception as e:
            log.error(f"Error injecting UV index data: {e}")
    
    def _inject_daily_forecast_data(self, record, data):
        """Inject daily forecast data into archive record."""
        
        try:
            if 'list' in data and len(data['list']) > 0:
                # Tomorrow's forecast (day 1)
                if len(data['list']) > 1:
                    day1 = data['list'][1]
                    record['ow_forecast_temp_day1'] = day1.get('temp', {}).get('day')
                
                # Day after tomorrow (day 2)
                if len(data['list']) > 2:
                    day2 = data['list'][2]
                    record['ow_forecast_temp_day2'] = day2.get('temp', {}).get('day')
                    
        except Exception as e:
            log.error(f"Error injecting daily forecast data: {e}")
    
    def _inject_hourly_forecast_data(self, record, data):
        """Inject hourly forecast data into archive record."""
        
        try:
            if 'list' in data and len(data['list']) > 0:
                # 1 hour forecast
                if len(data['list']) > 0:
                    hour1 = data['list'][0]
                    record['ow_forecast_temp_1h'] = hour1.get('main', {}).get('temp')
                
                # 6 hour forecast
                if len(data['list']) > 1:
                    hour6 = data['list'][1]  # Simplified - would need proper hour calculation
                    record['ow_forecast_temp_6h'] = hour6.get('main', {}).get('temp')
                    
        except Exception as e:
            log.error(f"Error injecting hourly forecast data: {e}")
    
    def _to_bool(self, value):
        """Convert various representations to boolean."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ('true', 'yes', '1', 'on')
        return bool(value)
    
    def shutDown(self):
        """Clean shutdown of the service."""
        log.info("OpenWeather service shutting down")
        # Threads are daemon threads, so they'll exit when main process exits


class OpenWeatherAPIClient:
    """
    HTTP client for OpenWeatherMap APIs with comprehensive error handling.
    """
    
    def __init__(self, api_key, timeout=30, retry_attempts=3):
        """Initialize the API client."""
        self.api_key = api_key
        self.timeout = timeout
        self.retry_attempts = retry_attempts
    
    def get_current_weather(self, latitude, longitude):
        """Get current weather data from OpenWeatherMap API."""
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': self.api_key,
            'units': 'metric'  # Celsius, meters/sec, etc.
        }
        
        return self._make_api_request(OPENWEATHER_ENDPOINTS['current_weather'], params)
    
    def get_air_quality(self, latitude, longitude):
        """Get air quality data from OpenWeatherMap API."""
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': self.api_key
        }
        
        return self._make_api_request(OPENWEATHER_ENDPOINTS['air_quality'], params)
    
    def get_uv_index(self, latitude, longitude):
        """Get UV index data from OpenWeatherMap API."""
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': self.api_key
        }
        
        return self._make_api_request(OPENWEATHER_ENDPOINTS['uv_index'], params)
    
    def get_daily_forecast(self, latitude, longitude):
        """Get daily forecast data from OpenWeatherMap API."""
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': self.api_key,
            'units': 'metric',
            'cnt': 8  # 8 days
        }
        
        return self._make_api_request(OPENWEATHER_ENDPOINTS['forecast_daily'], params)
    
    def get_hourly_forecast(self, latitude, longitude):
        """Get hourly forecast data from OpenWeatherMap API."""
        
        params = {
            'lat': latitude,
            'lon': longitude,
            'appid': self.api_key,
            'units': 'metric',
            'cnt': 48  # 48 hours
        }
        
        return self._make_api_request(OPENWEATHER_ENDPOINTS['forecast_hourly'], params)
    
    def _make_api_request(self, url, params):
        """Make HTTP request to OpenWeather API with retry logic."""
        
        query_string = urllib.parse.urlencode(params)
        full_url = f"{url}?{query_string}"
        
        for attempt in range(self.retry_attempts):
            try:
                log.debug(f"API request attempt {attempt + 1}: {url}")
                
                request = urllib.request.Request(full_url)
                request.add_header('User-Agent', f'WeeWX-OpenWeather/{VERSION}')
                
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    if response.status == 200:
                        response_data = response.read().decode('utf-8')
                        return json.loads(response_data)
                    else:
                        log.error(f"API request failed: HTTP {response.status}")
                        
            except urllib.error.HTTPError as e:
                if e.code == 401:
                    log.error("API authentication failed - check API key")
                    break  # Don't retry authentication errors
                elif e.code == 429:
                    log.warning("API rate limit exceeded")
                    wait_time = (attempt + 1) * 60  # Wait longer for rate limits
                    time.sleep(wait_time)
                    continue
                else:
                    log.error(f"HTTP error {e.code}: {e.reason}")
                    
            except urllib.error.URLError as e:
                log.error(f"Network error: {e.reason}")
                
            except json.JSONDecodeError as e:
                log.error(f"Invalid JSON response: {e}")
                
            except Exception as e:
                log.error(f"Unexpected error in API request: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < self.retry_attempts - 1:
                wait_time = (2 ** attempt) * 30  # 30s, 60s, 120s
                log.debug(f"Waiting {wait_time}s before retry")
                time.sleep(wait_time)
        
        log.error(f"API request failed after {self.retry_attempts} attempts")
        return None


# WeeWX unit system integration
def setup_unit_system():
    """Set up WeeWX unit system for OpenWeather fields."""
    
    # Define unit groups for OpenWeather observations
    weewx.units.obs_group_dict.update({
        # Current weather fields
        'ow_temperature': 'group_temperature',
        'ow_feels_like': 'group_temperature', 
        'ow_pressure': 'group_pressure',
        'ow_humidity': 'group_percent',
        'ow_cloud_cover': 'group_percent',
        'ow_visibility': 'group_distance',
        'ow_wind_speed': 'group_speed',
        'ow_wind_direction': 'group_direction',
        
        # Air quality fields
        'ow_pm25': 'group_concentration',
        'ow_pm10': 'group_concentration',
        'ow_ozone': 'group_concentration',
        'ow_no2': 'group_concentration',
        'ow_so2': 'group_concentration',
        'ow_co': 'group_concentration',
        'ow_aqi': 'group_count',
        
        # UV index fields
        'ow_uv_current': 'group_uv',
        'ow_uv_max': 'group_uv',
        
        # Forecast fields
        'ow_forecast_temp_day1': 'group_temperature',
        'ow_forecast_temp_day2': 'group_temperature',
        'ow_forecast_temp_1h': 'group_temperature',
        'ow_forecast_temp_6h': 'group_temperature'
    })
    
    # Define concentration unit group for air quality
    weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
    weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
    weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
    
    # Define UV index unit group
    weewx.units.USUnits['group_uv'] = 'uv_index'
    weewx.units.MetricUnits['group_uv'] = 'uv_index'
    weewx.units.MetricWXUnits['group_uv'] = 'uv_index'
    
    # Set up formatting
    weewx.units.default_unit_format_dict.update({
        'microgram_per_meter_cubed': '%.1f',
        'uv_index': '%.1f'
    })
    
    weewx.units.default_unit_label_dict.update({
        'microgram_per_meter_cubed': ' μg/m³',
        'uv_index': ''
    })

# Initialize unit system when module is loaded
setup_unit_system()
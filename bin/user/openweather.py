#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension - Complete Service Implementation
Integrates OpenWeatherMap APIs for current weather and air quality data

Copyright (C) 2025 WeeWX OpenWeather Extension
Licensed under GNU General Public License v3
"""

import json
import time
import threading
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, Optional, Any

import weewx
import weewx.units
from weewx.engine import StdService

# Version and metadata
VERSION = "1.0.0"
DRIVER_NAME = "OpenWeather"


class OpenWeatherDataCollector:
    """Handles API calls to OpenWeather for current weather and air quality data."""
    
    def __init__(self, api_key: str, latitude: float, longitude: float, timeout: int = 30):
        self.api_key = api_key
        self.latitude = latitude
        self.longitude = longitude
        self.timeout = timeout
        
        # API endpoints
        self.current_weather_url = "http://api.openweathermap.org/data/2.5/weather"
        self.air_quality_url = "http://api.openweathermap.org/data/2.5/air_pollution"
        
    def collect_current_weather(self) -> Optional[Dict[str, Any]]:
        """
        Collect current weather data from OpenWeather API.
        
        Returns:
            Dictionary with ow_ prefixed fields or None if failed
        """
        try:
            # Build request parameters
            params = {
                'lat': str(self.latitude),
                'lon': str(self.longitude),
                'appid': self.api_key,
                'units': 'metric'  # Celsius, m/s wind speed, metric visibility
            }
            
            # Make API request
            url = f"{self.current_weather_url}?{urllib.parse.urlencode(params)}"
            
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.status != 200:
                    raise urllib.error.HTTPError(url, response.status, f"HTTP {response.status}", None, None)
                
                data = json.loads(response.read().decode('utf-8'))
            
            # Validate response structure
            if not self._validate_weather_response(data):
                return None
                
            # Extract and map weather data with ow_ prefix
            weather_data = {}
            
            # Temperature data (convert Celsius to system units will be handled by WeeWX)
            if 'main' in data:
                main = data['main']
                weather_data['ow_temperature'] = main.get('temp')
                weather_data['ow_feels_like'] = main.get('feels_like')
                weather_data['ow_pressure'] = main.get('pressure')  # hPa
                weather_data['ow_humidity'] = main.get('humidity')  # %
                weather_data['ow_temp_min'] = main.get('temp_min')
                weather_data['ow_temp_max'] = main.get('temp_max')
                weather_data['ow_sea_level'] = main.get('sea_level')
                weather_data['ow_grnd_level'] = main.get('grnd_level')
            
            # Visibility (meters)
            weather_data['ow_visibility'] = data.get('visibility')
            
            # Wind data
            if 'wind' in data:
                wind = data['wind']
                weather_data['ow_wind_speed'] = wind.get('speed')  # m/s
                weather_data['ow_wind_direction'] = wind.get('deg')  # degrees
                weather_data['ow_wind_gust'] = wind.get('gust')  # m/s
            
            # Cloud cover
            if 'clouds' in data:
                weather_data['ow_cloud_cover'] = data['clouds'].get('all')  # %
            
            # Precipitation (if present)
            if 'rain' in data:
                weather_data['ow_rain_1h'] = data['rain'].get('1h')  # mm
                weather_data['ow_rain_3h'] = data['rain'].get('3h')  # mm
                
            if 'snow' in data:
                weather_data['ow_snow_1h'] = data['snow'].get('1h')  # mm
                weather_data['ow_snow_3h'] = data['snow'].get('3h')  # mm
            
            # Weather description
            if 'weather' in data and len(data['weather']) > 0:
                weather_info = data['weather'][0]
                weather_data['ow_weather_main'] = weather_info.get('main')
                weather_data['ow_weather_description'] = weather_info.get('description')
                weather_data['ow_weather_icon'] = weather_info.get('icon')
            
            # Data timestamp
            weather_data['ow_weather_timestamp'] = data.get('dt')
            
            return weather_data
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Exception(f"OpenWeather API authentication failed - check API key")
            elif e.code == 429:
                raise Exception(f"OpenWeather API rate limit exceeded")
            else:
                raise Exception(f"OpenWeather API HTTP error {e.code}: {e.reason}")
                
        except urllib.error.URLError as e:
            raise Exception(f"OpenWeather API network error: {e.reason}")
            
        except json.JSONDecodeError as e:
            raise Exception(f"OpenWeather API response parsing error: {e}")
            
        except Exception as e:
            raise Exception(f"OpenWeather current weather collection failed: {e}")
    
    def collect_air_quality(self) -> Optional[Dict[str, Any]]:
        """
        Collect air quality data from OpenWeather API.
        
        Returns:
            Dictionary with ow_ prefixed fields or None if failed
        """
        try:
            # Build request parameters
            params = {
                'lat': str(self.latitude),
                'lon': str(self.longitude),
                'appid': self.api_key
            }
            
            # Make API request
            url = f"{self.air_quality_url}?{urllib.parse.urlencode(params)}"
            
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                if response.status != 200:
                    raise urllib.error.HTTPError(url, response.status, f"HTTP {response.status}", None, None)
                
                data = json.loads(response.read().decode('utf-8'))
            
            # Validate response structure
            if not self._validate_air_quality_response(data):
                return None
                
            # Extract air quality data with ow_ prefix
            air_quality_data = {}
            
            if 'list' in data and len(data['list']) > 0:
                current_pollution = data['list'][0]
                
                # OpenWeather AQI (1-5 scale)
                if 'main' in current_pollution:
                    air_quality_data['ow_aqi'] = current_pollution['main'].get('aqi')
                
                # Individual pollutants (μg/m³)
                if 'components' in current_pollution:
                    components = current_pollution['components']
                    air_quality_data['ow_pm25'] = components.get('pm2_5')  # PM2.5
                    air_quality_data['ow_pm10'] = components.get('pm10')   # PM10
                    air_quality_data['ow_ozone'] = components.get('o3')    # Ozone
                    air_quality_data['ow_no2'] = components.get('no2')     # Nitrogen dioxide
                    air_quality_data['ow_so2'] = components.get('so2')     # Sulfur dioxide
                    air_quality_data['ow_co'] = components.get('co')       # Carbon monoxide
                    air_quality_data['ow_nh3'] = components.get('nh3')     # Ammonia
                    air_quality_data['ow_no'] = components.get('no')       # Nitrogen monoxide
                
                # Data timestamp
                air_quality_data['ow_air_quality_timestamp'] = current_pollution.get('dt')
            
            return air_quality_data
            
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise Exception(f"OpenWeather API authentication failed - check API key")
            elif e.code == 429:
                raise Exception(f"OpenWeather API rate limit exceeded")
            else:
                raise Exception(f"OpenWeather API HTTP error {e.code}: {e.reason}")
                
        except urllib.error.URLError as e:
            raise Exception(f"OpenWeather API network error: {e.reason}")
            
        except json.JSONDecodeError as e:
            raise Exception(f"OpenWeather API response parsing error: {e}")
            
        except Exception as e:
            raise Exception(f"OpenWeather air quality collection failed: {e}")
    
    def _validate_weather_response(self, data: Dict[str, Any]) -> bool:
        """Validate current weather API response structure."""
        required_keys = ['coord', 'main']
        return all(key in data for key in required_keys)
    
    def _validate_air_quality_response(self, data: Dict[str, Any]) -> bool:
        """Validate air quality API response structure."""
        if 'list' not in data or not data['list']:
            return False
        
        first_entry = data['list'][0]
        return 'main' in first_entry and 'components' in first_entry


class OpenWeatherBackgroundThread(threading.Thread):
    """Background thread for collecting OpenWeather data with individual module timing."""
    
    def __init__(self, service_instance):
        super(OpenWeatherBackgroundThread, self).__init__()
        self.daemon = True
        self.service = service_instance
        self.shutdown_event = threading.Event()
        
        # Individual module timing
        self.last_weather_call = 0
        self.last_air_quality_call = 0
        
        # Get intervals from configuration
        intervals = self.service.config.get('intervals', {})
        self.weather_interval = intervals.get('current_weather', 3600)
        self.air_quality_interval = intervals.get('air_quality', 7200)
        
        # Check enabled modules
        modules = self.service.config.get('modules', {})
        self.weather_enabled = modules.get('current_weather', False)
        self.air_quality_enabled = modules.get('air_quality', False)
        
        self.service.log.info(f"OpenWeather background thread initialized:")
        self.service.log.info(f"  Current weather: {'enabled' if self.weather_enabled else 'disabled'} (interval: {self.weather_interval}s)")
        self.service.log.info(f"  Air quality: {'enabled' if self.air_quality_enabled else 'disabled'} (interval: {self.air_quality_interval}s)")
    
    def run(self):
        """Main thread loop with individual module timing."""
        self.service.log.info("OpenWeather background thread started")
        
        while not self.shutdown_event.is_set():
            try:
                current_time = time.time()
                
                # Check if current weather data should be collected
                if (self.weather_enabled and 
                    current_time - self.last_weather_call >= self.weather_interval):
                    
                    self._collect_weather_data()
                    self.last_weather_call = current_time
                
                # Check if air quality data should be collected
                if (self.air_quality_enabled and 
                    current_time - self.last_air_quality_call >= self.air_quality_interval):
                    
                    self._collect_air_quality_data()
                    self.last_air_quality_call = current_time
                
                # Sleep for 60 seconds before next check
                if not self.shutdown_event.wait(60):
                    continue
                else:
                    break
                    
            except Exception as e:
                self.service.log.error(f"OpenWeather background thread error: {e}")
                # Continue running even on errors
                if not self.shutdown_event.wait(300):  # Wait 5 minutes on error
                    continue
                else:
                    break
        
        self.service.log.info("OpenWeather background thread stopped")
    
    def _collect_weather_data(self):
        """Collect current weather data and store in thread-safe manner."""
        try:
            weather_data = self.service.data_collector.collect_current_weather()
            
            if weather_data:
                with self.service.data_lock:
                    self.service.latest_weather_data.update(weather_data)
                    self.service.latest_weather_data['collection_timestamp'] = time.time()
                
                if self.service.config.get('log_success', False):
                    temp = weather_data.get('ow_temperature')
                    humidity = weather_data.get('ow_humidity')
                    pressure = weather_data.get('ow_pressure')
                    self.service.log.info(
                        f"Collected current weather: temp={temp}°C, "
                        f"humidity={humidity}%, pressure={pressure}hPa"
                    )
            else:
                self.service.log.warning("Current weather data collection returned no data")
                
        except Exception as e:
            if self.service.config.get('log_errors', True):
                self.service.log.error(f"Current weather collection failed: {e}")
    
    def _collect_air_quality_data(self):
        """Collect air quality data and store in thread-safe manner."""
        try:
            air_quality_data = self.service.data_collector.collect_air_quality()
            
            if air_quality_data:
                with self.service.data_lock:
                    self.service.latest_air_quality_data.update(air_quality_data)
                    self.service.latest_air_quality_data['collection_timestamp'] = time.time()
                
                if self.service.config.get('log_success', False):
                    aqi = air_quality_data.get('ow_aqi')
                    pm25 = air_quality_data.get('ow_pm25')
                    pm10 = air_quality_data.get('ow_pm10')
                    self.service.log.info(
                        f"Collected air quality: AQI={aqi}, "
                        f"PM2.5={pm25}μg/m³, PM10={pm10}μg/m³"
                    )
            else:
                self.service.log.warning("Air quality data collection returned no data")
                
        except Exception as e:
            if self.service.config.get('log_errors', True):
                self.service.log.error(f"Air quality collection failed: {e}")
    
    def shutdown(self):
        """Signal the thread to shutdown gracefully."""
        self.service.log.info("Shutting down OpenWeather background thread...")
        self.shutdown_event.set()


class OpenWeatherService(StdService):
    """Main OpenWeather service integrating current weather and air quality data collection."""
    
    def __init__(self, engine, config_dict):
        super(OpenWeatherService, self).__init__(engine, config_dict)
        
        try:
            # Parse configuration
            self.config = config_dict.get('OpenWeatherService', {})
            
            # Setup unit system integration
            self._setup_unit_system()
            
            # Validate required configuration
            if not self.config.get('enable', True):
                self.log.info("OpenWeather service disabled in configuration")
                return
            
            api_key = self.config.get('api_key')
            if not api_key or api_key == 'REPLACE_ME':
                raise ValueError("OpenWeather API key not configured")
            
            # Get station coordinates
            station_config = config_dict.get('Station', {})
            latitude = float(station_config.get('latitude', 0.0))
            longitude = float(station_config.get('longitude', 0.0))
            
            if latitude == 0.0 and longitude == 0.0:
                raise ValueError("Station coordinates not configured")
            
            # Initialize data collector
            timeout = self.config.get('timeout', 30)
            self.data_collector = OpenWeatherDataCollector(api_key, latitude, longitude, timeout)
            
            # Thread-safe data storage
            self.data_lock = threading.Lock()
            self.latest_weather_data = {}
            self.latest_air_quality_data = {}
            
            # Start background data collection thread
            self.background_thread = OpenWeatherBackgroundThread(self)
            self.background_thread.start()
            
            # Bind to archive events
            self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
            
            self.log.info(f"OpenWeather service initialized for coordinates {latitude}, {longitude}")
            
        except Exception as e:
            self.log.error(f"OpenWeather service initialization failed: {e}")
            raise
    
    def _setup_unit_system(self):
        """Setup unit system integration for OpenWeather fields."""
        
        # Define new unit groups for OpenWeather data
        weewx.units.USUnits.setdefault('group_concentration', 'microgram_per_meter_cubed')
        weewx.units.MetricUnits.setdefault('group_concentration', 'microgram_per_meter_cubed')
        weewx.units.MetricWXUnits.setdefault('group_concentration', 'microgram_per_meter_cubed')
        
        weewx.units.USUnits.setdefault('group_aqi', 'aqi')
        weewx.units.MetricUnits.setdefault('group_aqi', 'aqi')
        weewx.units.MetricWXUnits.setdefault('group_aqi', 'aqi')
        
        # Map observation types to unit groups
        unit_mappings = {
            # Temperature fields
            'ow_temperature': 'group_temperature',
            'ow_feels_like': 'group_temperature',
            'ow_temp_min': 'group_temperature',
            'ow_temp_max': 'group_temperature',
            
            # Pressure fields
            'ow_pressure': 'group_pressure',
            'ow_sea_level': 'group_pressure',
            'ow_grnd_level': 'group_pressure',
            
            # Humidity
            'ow_humidity': 'group_percent',
            
            # Wind fields
            'ow_wind_speed': 'group_speed',
            'ow_wind_direction': 'group_direction',
            'ow_wind_gust': 'group_speed',
            
            # Cloud cover
            'ow_cloud_cover': 'group_percent',
            
            # Visibility
            'ow_visibility': 'group_distance',
            
            # Precipitation
            'ow_rain_1h': 'group_rain',
            'ow_rain_3h': 'group_rain',
            'ow_snow_1h': 'group_rain',
            'ow_snow_3h': 'group_rain',
            
            # Weather description fields
            'ow_weather_main': 'group_count',
            'ow_weather_description': 'group_count',
            'ow_weather_icon': 'group_count',
            
            # Air quality fields - pollutant concentrations
            'ow_pm25': 'group_concentration',
            'ow_pm10': 'group_concentration',
            'ow_ozone': 'group_concentration',
            'ow_no2': 'group_concentration',
            'ow_so2': 'group_concentration',
            'ow_co': 'group_concentration',
            'ow_nh3': 'group_concentration',
            'ow_no': 'group_concentration',
            
            # Air quality index
            'ow_aqi': 'group_aqi',
            
            # Timestamps
            'ow_weather_timestamp': 'group_time',
            'ow_air_quality_timestamp': 'group_time',
        }
        
        # Apply unit mappings
        for obs_type, unit_group in unit_mappings.items():
            weewx.units.obs_group_dict[obs_type] = unit_group
        
        # Define unit labels and formatting
        unit_labels = {
            'microgram_per_meter_cubed': ' μg/m³',
            'aqi': ' AQI',
        }
        
        unit_formats = {
            'microgram_per_meter_cubed': '%.1f',
            'aqi': '%.0f',
        }
        
        for unit, label in unit_labels.items():
            weewx.units.default_unit_label_dict[unit] = label
            
        for unit, format_str in unit_formats.items():
            weewx.units.default_unit_format_dict[unit] = format_str
    
    def new_archive_record(self, event):
        """Inject OpenWeather data into archive records."""
        if not self.config.get('enable', True):
            return
        
        try:
            # Get latest data (thread-safe)
            with self.data_lock:
                weather_data = self.latest_weather_data.copy()
                air_quality_data = self.latest_air_quality_data.copy()
            
            # Check data freshness and inject
            max_age = self.config.get('max_data_age', 7200)  # 2 hours default
            current_time = time.time()
            
            # Inject weather data if fresh
            weather_timestamp = weather_data.get('collection_timestamp', 0)
            if current_time - weather_timestamp <= max_age:
                for key, value in weather_data.items():
                    if key != 'collection_timestamp' and value is not None:
                        event.record[key] = value
            
            # Inject air quality data if fresh
            air_quality_timestamp = air_quality_data.get('collection_timestamp', 0)
            if current_time - air_quality_timestamp <= max_age:
                for key, value in air_quality_data.items():
                    if key != 'collection_timestamp' and value is not None:
                        event.record[key] = value
            
            # Log successful injection if configured
            if self.config.get('log_success', False):
                injected_fields = []
                if weather_timestamp and current_time - weather_timestamp <= max_age:
                    injected_fields.append("weather")
                if air_quality_timestamp and current_time - air_quality_timestamp <= max_age:
                    injected_fields.append("air_quality")
                
                if injected_fields:
                    self.log.debug(f"Injected OpenWeather data: {', '.join(injected_fields)}")
            
        except Exception as e:
            if self.config.get('log_errors', True):
                self.log.error(f"OpenWeather data injection failed: {e}")
    
    def shutDown(self):
        """Clean shutdown of the service."""
        try:
            if hasattr(self, 'background_thread'):
                self.background_thread.shutdown()
                self.background_thread.join(timeout=10)
                
            self.log.info("OpenWeather service shutdown complete")
            
        except Exception as e:
            self.log.error(f"OpenWeather service shutdown error: {e}")


# WeeWX service entry point
def loader(config_dict, engine):
    """Load the OpenWeather service."""
    return OpenWeatherService(engine, config_dict)
# WeeWX OpenWeather Extension

A comprehensive WeeWX extension that integrates OpenWeatherMap APIs to provide weather and air quality data with modular configuration and efficient API usage.

## Features

- **Current Weather Data**: Temperature, humidity, pressure, wind, cloud cover, visibility
- **Air Quality Data**: PM2.5, PM10, O₃, NO₂, SO₂, CO, NH₃, OpenWeather AQI (1-5 scale)
- **UV Index**: Current UV radiation data
- **Forecast Data**: Daily and hourly forecasts (framework ready)
- **Modular Configuration**: Enable only the data modules you need
- **Rate Limit Management**: Efficient API usage with configurable intervals
- **Multi-Source Support**: Works alongside local weather stations
- **Thread-Safe Operation**: Non-blocking background data collection

## Requirements

- WeeWX 5.1 or later
- Python 3.7 or later
- OpenWeatherMap API key (free registration available)
- Internet connection for API access

## Quick Start

1. **Get API Key**: Register at [OpenWeatherMap](https://openweathermap.org/api) for free API access
2. **Install Extension**: `weectl extension install weewx-openweather.zip`
3. **Follow Installation Prompts**: Configure API key and select modules
4. **Restart WeeWX**: `sudo systemctl restart weewx`

## Installation

### Method 1: Extension Installer (Recommended)
```bash
# Download latest release
wget https://github.com/YOUR_USERNAME/weewx-openweather/releases/latest/download/weewx-openweather.zip

# Install with interactive configuration
weectl extension install weewx-openweather.zip

# Follow prompts to:
# - Enter OpenWeatherMap API key
# - Select data modules to enable
# - Configure API call intervals
# - Automatically create database fields

# Restart WeeWX
sudo systemctl restart weewx
```

### Method 2: Manual Installation
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/weewx-openweather.git
cd weewx-openweather

# Create package
zip -r weewx-openweather.zip install.py bin/ README.md CHANGELOG.md MANIFEST

# Install
weectl extension install weewx-openweather.zip
```

## Interactive Installation Process

The installer provides a guided setup experience:

### 1. **Station Coordinates Validation**
```
Validating station coordinates...
✓ Station coordinates: 33.656915, -117.982542
```

### 2. **API Key Configuration**
```
OpenWeatherMap API Key Configuration
----------------------------------------
Get a free API key at: https://openweathermap.org/api
Free tier includes 1,000 calls/day (sufficient for this extension)

Enter your OpenWeatherMap API key: [your-32-character-key]
✓ API key accepted: 1a2b3c4d...
```

### 3. **Module Selection**
```
Module Configuration
--------------------
Select which OpenWeather data modules to enable:

current_weather:
  Description: Current weather (temperature, humidity, pressure, wind, clouds)
  Recommended for all users
Enable current_weather? [Y/n]: Y
  ✓ current_weather enabled

air_quality:
  Description: Air quality data (PM2.5, PM10, ozone, NO2, gases, AQI)
  Recommended for health monitoring
Enable air_quality? [Y/n]: Y
  ✓ air_quality enabled

uv_index:
  Description: UV radiation data (current and daily maximum)
  Optional - useful for outdoor activities
Enable uv_index? [y/N]: n
  - uv_index disabled
```

### 4. **API Call Intervals**
```
API Call Interval Configuration
--------------------------------
Configure how often to call OpenWeather APIs:
• Free tier: 1,000 calls/day limit
• Recommended intervals stay well within limits

current_weather:
  Recommended interval: 3600 seconds (24 calls/day)
Use recommended interval? [Y/n]: Y
✓ Using recommended interval

Total estimated daily API calls: 36
✓ API usage well within free tier limits
```

### 5. **Database Schema Creation**
```
Database Schema Management
==========================
Checking and extending database schema...

Adding missing fields to database:
  Adding field 'ow_temperature' (REAL)...
    ✓ Successfully added 'ow_temperature'
  Adding field 'ow_pm25' (REAL)...
    ✓ Successfully added 'ow_pm25'
  [additional fields...]

✓ Database schema management completed successfully
```

## Configuration

After installation, your configuration will look like this:

### Automatic Configuration Created
```ini
[OpenWeatherService]
    enable = true
    api_key = YOUR_API_KEY_HERE
    log_success = false
    log_errors = true
    timeout = 30
    retry_attempts = 3
    
    # Modules enabled during installation
    [[modules]]
        current_weather = true
        air_quality = true
        uv_index = false
        forecast_daily = false
        forecast_hourly = false
    
    # API call intervals configured during installation
    [[intervals]]
        current_weather = 3600    # 1 hour (24 calls/day)
        air_quality = 7200        # 2 hours (12 calls/day)
        uv_index = 3600           # 1 hour (24 calls/day)
        forecast_daily = 21600    # 6 hours (4 calls/day)
        forecast_hourly = 3600    # 1 hour (24 calls/day)

# Service automatically registered during installation
[Engine]
    [[Services]]
        data_services = user.openweather.OpenWeatherService, weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC
```

### Manual Configuration (Optional)
You can modify the configuration after installation:

```ini
[OpenWeatherService]
    # Enable/disable the entire service
    enable = true
    
    # Your OpenWeatherMap API key
    api_key = YOUR_32_CHARACTER_API_KEY
    
    # Logging preferences
    log_success = false    # Log successful data collection
    log_errors = true      # Log errors and warnings
    
    # HTTP request settings
    timeout = 30           # Request timeout in seconds
    retry_attempts = 3     # Number of retry attempts
    
    # Enable/disable specific modules
    [[modules]]
        current_weather = true     # Temperature, humidity, pressure, wind
        air_quality = true         # PM2.5, PM10, ozone, gases, AQI
        uv_index = false          # UV radiation data
        forecast_daily = false    # 8-day daily forecasts
        forecast_hourly = false   # 48-hour hourly forecasts
    
    # API call intervals (seconds)
    [[intervals]]
        current_weather = 3600    # 1 hour - current conditions
        air_quality = 7200        # 2 hours - air quality changes slowly
        uv_index = 3600           # 1 hour - UV changes throughout day
        forecast_daily = 21600    # 6 hours - daily forecasts
        forecast_hourly = 3600    # 1 hour - hourly forecasts
```

## Database Fields

All fields use the `ow_` prefix to avoid conflicts. Fields are created automatically during installation based on enabled modules:

### Current Weather Module
- `ow_temperature` (°C) - Current temperature
- `ow_feels_like` (°C) - Feels like temperature
- `ow_pressure` (hPa) - Atmospheric pressure
- `ow_humidity` (%) - Relative humidity
- `ow_cloud_cover` (%) - Cloud cover percentage (0-100%)
- `ow_visibility` (m) - Visibility distance
- `ow_wind_speed` (m/s) - Wind speed
- `ow_wind_direction` (°) - Wind direction (degrees)

### Air Quality Module
- `ow_pm25` (μg/m³) - PM2.5 concentration
- `ow_pm10` (μg/m³) - PM10 concentration
- `ow_ozone` (μg/m³) - Ozone concentration
- `ow_no2` (μg/m³) - NO₂ concentration
- `ow_so2` (μg/m³) - SO₂ concentration
- `ow_co` (μg/m³) - CO concentration
- `ow_aqi` (1-5) - OpenWeather AQI (European scale)

### UV Index Module
- `ow_uv_current` - Current UV index
- `ow_uv_max` - Daily maximum UV index

### Forecast Modules (Framework Ready)
- `ow_forecast_temp_day1` (°C) - Tomorrow's temperature
- `ow_forecast_temp_day2` (°C) - Day 2 temperature
- `ow_forecast_temp_1h` (°C) - 1-hour forecast temperature
- `ow_forecast_temp_6h` (°C) - 6-hour forecast temperature

## API Usage and Rate Limits

### Free Tier Limits
- **Daily**: 1,000 calls/day
- **Per minute**: 60 calls/minute
- **Geographic**: Global coverage
- **Historical data**: Not included in free tier

### Recommended Usage Patterns
| Module | Interval | Daily Calls | Rationale |
|--------|----------|-------------|-----------|
| Current Weather | 1 hour | 24 | Weather changes hourly |
| Air Quality | 2 hours | 12 | Air quality changes slowly |
| UV Index | 1 hour | 24 | UV varies throughout day |
| Daily Forecast | 6 hours | 4 | Daily forecasts stable |
| Hourly Forecast | 1 hour | 24 | For detailed planning |

**Total with all modules**: ~88 calls/day (well within 1,000 limit)

### Usage Monitoring
```bash
# Check API usage in WeeWX logs
sudo tail -f /var/log/weewx/weewx.log | grep OpenWeather

# Monitor daily usage
grep "OpenWeather" /var/log/weewx/weewx.log | grep "$(date +%Y-%m-%d)" | wc -l
```

## Data Sources

### OpenWeatherMap APIs Used
- **Current Weather API**: `api.openweathermap.org/data/2.5/weather`
- **Air Pollution API**: `api.openweathermap.org/data/2.5/air_pollution`
- **UV Index API**: `api.openweathermap.org/data/2.5/uvi`
- **Daily Forecast API**: `api.openweathermap.org/data/2.5/forecast/daily`
- **Hourly Forecast API**: `api.openweathermap.org/data/2.5/forecast`

### OpenWeather AQI Scale (European Standard)
OpenWeather uses a simplified 1-5 scale based on European standards:

| AQI | Level | Description | Example Conditions |
|-----|-------|-------------|-------------------|
| 1 | Good | Minimal pollution | Clear, clean air |
| 2 | Fair | Acceptable for most people | Slight haze |
| 3 | Moderate | Sensitive groups may experience symptoms | Noticeable pollution |
| 4 | Poor | Health warnings for everyone | Unhealthy air |
| 5 | Very Poor | Health alert for everyone | Hazardous conditions |

**Note**: This differs from the US EPA AQI scale (0-500). Raw pollutant concentrations are also provided for custom calculations.

## Integration with Other Extensions

This extension is designed to work with:
- **WeeWX CDC Surveillance Extension**: Public health surveillance data
- **WeeWX Environmental Health Extension**: Combined health risk assessment
- **Local weather stations**: Provides additional data fields
- **Air quality sensors**: Fallback/validation data sources

```ini
# Example combined configuration
[OpenWeatherService]
    # OpenWeather provides air quality data
    enable = true
    
[CDCSurveillanceService]
    # CDC provides disease surveillance
    enable = true
    
[EnvironmentalHealthService]
    # Combines both for health assessment
    enable = true
    air_quality_source = "openweather"
```

## Troubleshooting

### Common Issues

#### API Key Errors
```
Error: API authentication failed
```
**Solution**: 
1. Verify API key at https://openweathermap.org/api
2. Check that key is active (may take a few minutes after signup)
3. Ensure no extra spaces in configuration

#### Rate Limit Exceeded
```
Error: API rate limit exceeded (HTTP 429)
```
**Solution**: 
1. Increase intervals in configuration
2. Check total daily usage: `grep "OpenWeather" /var/log/weewx/weewx.log | wc -l`
3. Consider upgrading API plan if needed

#### No Data in Database
```
Check WeeWX logs: sudo tail -f /var/log/weewx/weewx.log
```
**Common causes**:
- API connectivity issues
- Missing database fields
- Service not started
- Configuration errors

#### Module Not Collecting Data
```
2025-01-21 10:00:00 weewx[1234]: INFO user.openweather: Successfully collected current_weather data
2025-01-21 10:00:00 weewx[1234]: WARNING user.openweather: Failed to collect air_quality data
```
**Solution**:
1. Check module is enabled in configuration
2. Verify API endpoints are accessible
3. Check for network connectivity issues

### Debug Mode
Enable detailed logging:
```ini
[OpenWeatherService]
    log_success = true
    log_errors = true

[Logging]
    [[loggers]]
        [[[user.openweather]]]
            level = DEBUG
```

### Test Scripts
```bash
# Test API connectivity manually
python3 -c "
import urllib.request, json
api_key = 'YOUR_API_KEY'
lat, lon = 33.656915, -117.982542
url = f'http://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={api_key}'
response = urllib.request.urlopen(url)
data = json.loads(response.read())
print('API Test Success:', data.get('name', 'Unknown'))
"

# Check database fields
weectl database show

# Validate configuration
weectl station show
```

### Manual Database Field Creation
If automatic field creation fails:
```bash
# Current weather fields
weectl database add-column ow_temperature --type REAL -y
weectl database add-column ow_feels_like --type REAL -y
weectl database add-column ow_pressure --type REAL -y
weectl database add-column ow_humidity --type REAL -y
weectl database add-column ow_cloud_cover --type REAL -y
weectl database add-column ow_visibility --type REAL -y
weectl database add-column ow_wind_speed --type REAL -y
weectl database add-column ow_wind_direction --type REAL -y

# Air quality fields
weectl database add-column ow_pm25 --type REAL -y
weectl database add-column ow_pm10 --type REAL -y
weectl database add-column ow_ozone --type REAL -y
weectl database add-column ow_no2 --type REAL -y
weectl database add-column ow_so2 --type REAL -y
weectl database add-column ow_co --type REAL -y
weectl database add-column ow_aqi --type INTEGER -y

# UV index fields
weectl database add-column ow_uv_current --type REAL -y
weectl database add-column ow_uv_max --type REAL -y
```

## Development

### Project Structure
```
weewx-openweather/
├── install.py                  # Extension installer
├── bin/user/
│   └── openweather.py         # Service implementation
├── README.md                  # This documentation
├── CHANGELOG.md              # Version history
└── MANIFEST                  # Package manifest
```

### Contributing
1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Make changes and test thoroughly
4. Update documentation if needed
5. Submit pull request with detailed description

### Development Setup
```bash
# Clone for development
git clone https://github.com/YOUR_USERNAME/weewx-openweather.git
cd weewx-openweather

# Test installation locally
zip -r weewx-openweather-dev.zip install.py bin/ README.md CHANGELOG.md MANIFEST
weectl extension install weewx-openweather-dev.zip

# View logs during development
sudo tail -f /var/log/weewx/weewx.log | grep -E "(OpenWeather|ERROR|WARNING)"
```

### Code Quality
- Follow PEP 8 Python style guidelines
- Add comprehensive error handling
- Test with various API conditions (success, failure, rate limits)
- Validate configuration edge cases
- Test database operations thoroughly

## Performance

### Resource Usage
- **Memory**: <10MB additional during normal operation
- **CPU**: Minimal impact, API calls run in background threads
- **Network**: ~1-5KB per API call depending on modules
- **Database**: <1KB per archive record for all fields

### Optimization Tips
1. **Enable only needed modules** - Reduces API calls and database size
2. **Adjust intervals** - Longer intervals reduce API usage
3. **Monitor logs** - Watch for errors or rate limiting
4. **Database maintenance** - Regular cleanup of old data if needed

## Support

- **Documentation**: This README and inline code comments
- **Issues**: Report bugs and feature requests on [GitHub Issues](https://github.com/YOUR_USERNAME/weewx-openweather/issues)
- **WeeWX Forum**: [WeeWX User Group](https://groups.google.com/g/weewx-user)
- **API Documentation**: [OpenWeatherMap API Docs](https://openweathermap.org/api)

## Changelog

### Version 1.0.0 (2025-01-21)
- Initial release
- Current weather data collection
- Air quality data collection
- UV index data collection
- Modular configuration system
- Interactive installation process
- Automatic database schema management
- Thread-safe background data collection
- Comprehensive error handling and retry logic

## Related Projects

- [WeeWX CDC Surveillance Extension](https://github.com/inguy24/weewx-cdc-surveillance) - Public health surveillance data
- [WeeWX Environmental Health Extension](https://github.com/inguy24/weewx-environmental-health) - Combined health risk assessment
- [WeeWX Main Project](https://github.com/weewx/weewx) - Weather station software framework

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE) file for details.

## Credits

- **WeeWX**: Weather station software framework by Tom Keffer and contributors
- **OpenWeatherMap**: Weather and air quality data provider
- **WeeWX Community**: Extensions development patterns and best practices

---

**Note**: This extension is part of a comprehensive environmental health monitoring framework. Consider installing all three extensions (OpenWeather, CDC Surveillance, Environmental Health) for complete environmental and health risk assessment capabilities.
# WeeWX OpenWeather Extension

A comprehensive WeeWX extension that integrates OpenWeatherMap APIs to provide weather and air quality data with modular configuration and efficient API usage.

## Features

- **Current Weather Data**: Temperature, humidity, pressure, wind, cloud cover, visibility
- **Air Quality Data**: PM2.5, PM10, O₃, NO₂, SO₂, CO, NH₃, OpenWeather AQI (1-5 scale)
- **UV Index**: Current and daily maximum UV radiation data
- **Forecast Data**: Daily (8-day) and hourly (48-hour) forecasts
- **Modular Configuration**: Enable only the data modules you need
- **Field Selection**: Choose specific fields to minimize database size
- **Rate Limit Management**: Efficient API usage with configurable intervals
- **Multi-Source Support**: Works alongside local weather stations

## Requirements

- WeeWX 5.1 or later
- Python 3.7 or later
- OpenWeatherMap API key (free registration available)
- Internet connection for API access

## Quick Start

1. **Get API Key**: Register at [OpenWeatherMap](https://openweathermap.org/api) for free API access
2. **Install Extension**: `weectl extension install weewx-openweather.zip`
3. **Configure**: Follow prompts to enter API key and select modules
4. **Restart WeeWX**: `sudo systemctl restart weewx`

## Installation

### Method 1: Extension Installer (Recommended)
```bash
# Download latest release
wget https://github.com/YOUR_USERNAME/weewx-openweather/releases/latest/download/weewx-openweather.zip

# Install with automatic configuration
weectl extension install weewx-openweather.zip

# Restart WeeWX
sudo systemctl restart weewx
```

### Method 2: Manual Installation
```bash
# Clone repository
git clone https://github.com/YOUR_USERNAME/weewx-openweather.git
cd weewx-openweather

# Create package
./scripts/create_package.sh

# Install
weectl extension install weewx-openweather-1.0.0.zip
```

## Configuration

The extension uses modular configuration to enable only the data you need:

### Basic Configuration
```ini
[OpenWeatherService]
    enable = true
    api_key = YOUR_API_KEY_HERE
    
    # Module selection
    [[modules]]
        current_weather = true      # Temperature, humidity, pressure, wind
        air_quality = true         # PM2.5, PM10, ozone, gases
        uv_index = false          # UV radiation data
        forecast_daily = false    # 8-day forecasts
        forecast_hourly = false   # 48-hour forecasts
    
    # API call intervals (seconds)
    [[intervals]]
        current_weather = 3600    # 1 hour
        air_quality = 7200       # 2 hours
        uv_index = 3600          # 1 hour
        forecast_daily = 21600   # 6 hours
        forecast_hourly = 3600   # 1 hour
```

### Advanced Field Selection
```yaml
# openweather_fields.yaml - Optional advanced configuration
field_selection:
  current_weather:
    temperature:
      temp = true
      feels_like = true
      temp_min = false
      temp_max = false
    atmospheric:
      pressure = true
      humidity = true
    sky_conditions:
      cloud_cover = true
      visibility = true
    wind:
      wind_speed = true
      wind_direction = true
      wind_gust = false
      
  air_quality:
    particulates:
      pm2_5 = true             # Primary health indicator
      pm10 = true              # Respiratory irritant
    gases:
      ozone = true             # Major asthma trigger
      nitrogen_dioxide = true  # Respiratory irritant
      sulfur_dioxide = false   # Optional
      carbon_monoxide = false  # Optional
    indices:
      openweather_aqi = true   # 1-5 scale
```

## Database Fields

All fields use the `ow_` prefix to avoid conflicts:

### Current Weather Module
- `ow_temperature` - Current temperature
- `ow_feels_like` - Feels like temperature
- `ow_pressure` - Atmospheric pressure
- `ow_humidity` - Relative humidity
- `ow_cloud_cover` - Cloud cover percentage (0-100%)
- `ow_visibility` - Visibility distance
- `ow_wind_speed` - Wind speed
- `ow_wind_direction` - Wind direction (degrees)

### Air Quality Module
- `ow_pm25` - PM2.5 concentration (μg/m³)
- `ow_pm10` - PM10 concentration (μg/m³)
- `ow_ozone` - Ozone concentration (μg/m³)
- `ow_no2` - NO₂ concentration (μg/m³)
- `ow_so2` - SO₂ concentration (μg/m³)
- `ow_co` - CO concentration (μg/m³)
- `ow_aqi` - OpenWeather AQI (1-5 scale)

### UV Index Module
- `ow_uv_current` - Current UV index
- `ow_uv_max` - Daily maximum UV index

## API Usage and Rate Limits

- **Free Tier**: 1,000 calls/day, 60 calls/minute
- **Recommended Intervals**: 
  - Current weather: 1 hour (24 calls/day)
  - Air quality: 2 hours (12 calls/day)
  - UV index: 1 hour (24 calls/day)
  - Total: ~60 calls/day (well within limits)

## Data Sources

### OpenWeatherMap APIs Used
- **Current Weather API**: `api.openweathermap.org/data/2.5/weather`
- **Air Pollution API**: `api.openweathermap.org/data/2.5/air_pollution`
- **UV Index API**: `api.openweathermap.org/data/2.5/uvi`
- **One Call API 3.0**: `api.openweathermap.org/data/3.0/onecall`

### OpenWeather AQI Scale (European Standard)
| AQI | Level | Description |
|-----|-------|-------------|
| 1 | Good | Minimal pollution |
| 2 | Fair | Acceptable for most people |
| 3 | Moderate | Sensitive groups may experience symptoms |
| 4 | Poor | Health warnings for everyone |
| 5 | Very Poor | Health alert for everyone |

## Integration with Other Extensions

This extension is designed to work with:
- **WeeWX CDC Surveillance Extension**: Public health surveillance data
- **WeeWX Environmental Health Extension**: Combined health risk assessment
- **Local weather stations**: Provides additional data fields
- **Air quality sensors**: Fallback/validation data sources

## Troubleshooting

### Common Issues

**API Key Errors**
```
Error: API authentication failed
Solution: Verify API key at https://openweathermap.org/api
```

**Rate Limit Exceeded**
```
Error: API rate limit exceeded
Solution: Increase intervals in configuration or upgrade API plan
```

**No Data in Database**
```
Check: WeeWX logs for service startup messages
Check: API connectivity with test script
Check: Database field creation during installation
```

### Debug Mode
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
# Test API connectivity
python3 examples/test_api.py YOUR_API_KEY 33.656915 -117.982542

# Validate configuration
python3 examples/validate_config.py

# Check database fields
python3 examples/check_database.py
```

## Development

### Project Structure
```
weewx-openweather/
├── bin/user/
│   └── openweather.py           # Main service implementation
├── examples/
│   ├── test_api.py             # API testing script
│   ├── validate_config.py      # Configuration validator
│   └── weewx.conf.example      # Example configuration
├── install.py                  # Extension installer
├── README.md                   # This file
├── CHANGELOG.md               # Version history
└── MANIFEST                   # Package manifest
```

### Contributing
1. Fork the repository
2. Create feature branch: `git checkout -b feature/new-feature`
3. Make changes and test thoroughly
4. Submit pull request with detailed description

### Running Tests
```bash
# Unit tests
python3 -m pytest tests/

# Integration tests (requires API key)
python3 tests/test_integration.py YOUR_API_KEY

# Code quality
flake8 bin/user/openweather.py
black bin/user/openweather.py
```

## Support

- **Documentation**: Full documentation in `docs/` directory
- **Issues**: Report bugs and feature requests on GitHub Issues
- **WeeWX Forum**: [WeeWX User Group](https://groups.google.com/g/weewx-user)
- **API Documentation**: [OpenWeatherMap API Docs](https://openweathermap.org/api)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

## Related Projects

- [WeeWX CDC Surveillance Extension](https://github.com/YOUR_USERNAME/weewx-cdc-surveillance)
- [WeeWX Environmental Health Extension](https://github.com/YOUR_USERNAME/weewx-environmental-health)
- [WeeWX Main Project](https://github.com/weewx/weewx)

## Credits

- **WeeWX**: Weather station software framework
- **OpenWeatherMap**: Weather and air quality data provider
- **Contributors**: See GitHub contributors list

---

**Note**: This extension is part of a comprehensive environmental health monitoring framework. Consider installing all three extensions for complete environmental and health risk assessment capabilities.
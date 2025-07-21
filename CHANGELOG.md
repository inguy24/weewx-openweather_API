# Changelog

All notable changes to the WeeWX OpenWeather Extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned Features
- One Call API 3.0 integration for enhanced forecasts
- Advanced field selection configuration
- Historical data backfill capabilities
- Custom AQI scale conversions (US EPA, UK, China)
- Weather alerts and warnings integration

## [1.0.0-alpha] - 2025-01-21

### Added
- **Alpha release** for community testing and feedback
- **Current Weather Data Collection**
  - Temperature (current and feels-like)
  - Atmospheric conditions (pressure, humidity)
  - Sky conditions (cloud cover, visibility)
  - Wind data (speed, direction)
- **Air Quality Data Collection**
  - Particulate matter (PM2.5, PM10)
  - Gases (O₃, NO₂, SO₂, CO, NH₃)
  - OpenWeather AQI (European 1-5 scale)
- **UV Index Data Collection**
  - Current UV radiation levels
  - Framework for daily maximum UV tracking
- **Modular Configuration System**
  - Enable/disable individual data modules
  - Configurable API call intervals per module
  - Rate limit management and usage calculation
- **Interactive Installation Process**
  - Guided API key configuration
  - Module selection with recommendations
  - Automatic interval configuration
  - Station coordinate validation
- **Robust Database Management**
  - Automatic field creation for enabled modules
  - Field existence checking and validation
  - Proper field type handling (REAL, INTEGER, TEXT)
  - Manual fallback commands when automation fails
- **Thread-Safe Background Collection**
  - Non-blocking API calls in separate threads
  - Thread-safe data storage with proper locking
  - Configurable collection intervals per module
  - Clean shutdown handling
- **Comprehensive Error Handling**
  - Exponential backoff retry logic (30s, 60s, 120s)
  - API authentication error detection
  - Rate limit handling (HTTP 429)
  - Network timeout and connection error recovery
  - Data staleness checking and validation
- **WeeWX Integration**
  - Proper StdService inheritance and event binding
  - Archive record injection with `ow_` field prefix
  - Unit system integration with proper formatting
  - Service registration through extension config
- **Production Features**
  - Configurable logging (success/error levels)
  - API usage monitoring and estimation
  - Data freshness validation
  - Memory efficient operation (<10MB)
- **User Experience**
  - Clear installation feedback and progress
  - Comprehensive troubleshooting documentation
  - Debug mode with detailed logging
  - Manual database setup instructions

### Technical Implementation
- **Base Service**: `weewx.engine.StdService` inheritance
- **Event Binding**: `weewx.NEW_ARCHIVE_RECORD` integration
- **API Client**: Custom HTTP client with retry logic
- **Database Fields**: 15+ fields with `ow_` prefix convention
- **Thread Management**: Daemon threads with proper lifecycle
- **Configuration**: Nested sections with type validation
- **Unit System**: μg/m³ for air quality, standard weather units

### API Endpoints Integrated
- **Current Weather**: `api.openweathermap.org/data/2.5/weather`
- **Air Pollution**: `api.openweathermap.org/data/2.5/air_pollution`
- **UV Index**: `api.openweathermap.org/data/2.5/uvi`
- **Forecast Framework**: Ready for daily/hourly forecast integration

### Database Schema
- **Current Weather Fields**: 8 fields (temperature, pressure, humidity, wind, clouds, visibility)
- **Air Quality Fields**: 7 fields (PM2.5, PM10, O₃, NO₂, SO₂, CO, AQI)
- **UV Index Fields**: 2 fields (current, daily maximum)
- **Forecast Fields**: Framework ready for expansion

### Rate Limiting & Performance
- **Free Tier Optimized**: Default configuration uses ~36 calls/day
- **Configurable Intervals**: 10-minute minimum with recommendations
- **Usage Estimation**: Automatic calculation and warnings
- **Efficient Collection**: Module-based API calls only when needed

### Dependencies
- **WeeWX**: 5.1 or later
- **Python**: 3.7 or later
- **API Key**: Free OpenWeatherMap registration required
- **Network**: Internet connection for API access

### Files Added
- `install.py` - Extension installer with interactive configuration
- `bin/user/openweather.py` - Service implementation (850+ lines)
- `README.md` - Comprehensive user documentation
- `CHANGELOG.md` - This version history
- `MANIFEST` - Package manifest file

### Configuration Structure
```ini
[OpenWeatherService]
    enable = true
    api_key = USER_PROVIDED
    modules = {current_weather, air_quality, uv_index, forecasts}
    intervals = {per-module timing configuration}
    timeout = 30
    retry_attempts = 3
    log_success = false
    log_errors = true
```

### Alpha Release Notes
This is an **alpha version** intended for testing by the WeeWX community. Please report bugs, issues, and feedback through GitHub Issues.

**Testing Needed:**
- Different WeeWX installations and configurations
- Various API usage patterns and rate limiting
- Database field creation across different schemas
- Error handling and recovery scenarios
- Performance under different system loads

### Known Limitations (Alpha)
- **Forecast Modules**: Framework implemented but not fully tested
- **Limited Testing**: Tested on limited WeeWX configurations
- **Documentation**: May require updates based on user feedback
- **Error Handling**: Some edge cases may not be covered

## Future Development

Development will continue based on community feedback and testing results from this alpha release. Focus will remain on the current work plan scope.

## Support and Contributing

- **Bug Reports**: [GitHub Issues](https://github.com/inguy24/weewx-openweather_API/issues)
- **Feature Requests**: [GitHub Issues](https://github.com/inguy24/weewx-openweather_API/issues) with enhancement label
- **Development**: Fork repository and submit pull requests
- **Documentation**: Improvements to README.md and inline comments welcome

---

*For installation and usage instructions, see [README.md](README.md)*
# WeeWX OpenWeather Extension

A comprehensive WeeWX extension that integrates OpenWeatherMap APIs to provide weather and air quality data with **interactive field selection** and efficient API usage.

**Author**: [Shane Burkhardt](https://github.com/inguy24)

## 🌟 Features

- **Interactive Field Selection**: Choose exactly which data fields you want during installation
- **Smart Complexity Levels**: 3 predefined levels from minimal (15 fields) to all fields (29 fields)
- **Custom Field Selection**: Advanced curses-based interface for precise field control
- **Dynamic Database Schema**: Only creates database fields for selected data
- **Current Weather Data**: Temperature, humidity, pressure, wind, cloud cover, visibility, precipitation
- **Air Quality Data**: PM2.5, PM10, O₃, NO₂, SO₂, CO, NH₃, NO, OpenWeather AQI (1-5 scale)
- **Weather Descriptions**: Complete weather categorization with icons
- **Unit System Integration**: Automatic WeeWX unit system detection and conversion
- **Modular Configuration**: Enable only the data modules you need
- **Rate Limit Management**: Efficient API usage with configurable intervals
- **Multi-Source Support**: Works alongside local weather stations  
- **Thread-Safe Operation**: Non-blocking background data collection
- **Robust Installation**: Automatic service registration and clean uninstall
- **Built-in Testing**: Comprehensive test suite for validation

## 📊 Field Selection System

### Complexity Levels

| Level | Fields | Description |
|-------|--------|-------------|
| **Minimal** | 15 fields | Essential fields for Extension 3 health predictions |
| **All Fields** | 29 fields | Complete OpenWeatherMap dataset with all available fields |
| **Custom** | Your choice | Interactive selection of specific fields |

### Benefits of Field Selection
- **Reduced Database Size**: Only store data you actually need
- **Faster Performance**: Less data processing and storage overhead
- **Cleaner Reports**: Focus on relevant metrics for your use case
- **API Efficiency**: Reduced processing of unused data

## 🚀 Installation

### Prerequisites
- WeeWX 5.1 or later
- Python 3.7 or later
- OpenWeatherMap API key (free registration available)
- Internet connection for API access

### Step 1: Get API Key
1. Visit [OpenWeatherMap](https://openweathermap.org/api)
2. Create free account  
3. Generate API key (usually active within 10 minutes)
4. Save your API key for installation

### Step 2: Install Extension

```bash
# Download latest release
wget https://github.com/inguy24/weewx-openweather_API/releases/latest/download/weewx-openweather.zip

# Install with interactive configuration
weectl extension install weewx-openweather.zip

# The installer will guide you through:
# 1. API key setup
# 2. Field selection (complexity level or custom)
# 3. Automatic database schema creation
# 4. Service registration

# Restart WeeWX
sudo systemctl restart weewx
```

## 🛠️ Interactive Installation Process

### 1. **API Key Configuration**
```
OPENWEATHERMAP API KEY SETUP
============================
You need a free API key from OpenWeatherMap.
1. Visit: https://openweathermap.org/api
2. Sign up for free account
3. Get your API key from the dashboard

Enter your OpenWeatherMap API key: [your-32-character-key]
✓ API key accepted: 1a2b3c4d...
```

### 2. **Unit System Detection**
```
UNIT SYSTEM DETECTION
---------------------
WeeWX unit system: US
OpenWeather API calls will use: imperial
→ Temperature: Fahrenheit, Wind: mph, Pressure: inHg

This ensures OpenWeather data integrates seamlessly with your WeeWX system.
```

### 3. **Field Selection**
```
OPENWEATHER DATA COLLECTION LEVEL
==================================

Choose which data fields to collect from OpenWeatherMap.
Each level includes specific fields as listed below:

1. MINIMAL COLLECTION
   Essential fields for Extension 3 health predictions
   15 database fields
   Fields: Temperature, humidity, pressure, wind speed, PM2.5, PM10, ozone, NO2, SO2, CO, AQI, wind direction

2. ALL FIELDS
   Complete OpenWeatherMap dataset with all available fields
   29 database fields
   Fields: All minimal fields plus feels-like temperature, daily min/max temp, wind gusts, cloud cover, 
           visibility, rain/snow data, weather descriptions, atmospheric details, ammonia, nitrogen monoxide

3. CUSTOM SELECTION
   Choose specific fields manually using interactive menu
   Select from 29 available fields

Enter choice [1-3]: 2
✓ Selected: All Fields (29 fields)
```

### 4. **Custom Field Selection** (if option 3 chosen)
Interactive curses-based interface for precise field control:
```
CUSTOM FIELD SELECTION - Select All Desired Fields
===================================================
↑↓:Navigate  SPACE:Toggle  ENTER:Confirm  q:Quit

  [ ] Current temperature
  [X] Feels-like temperature - SELECTED
  [ ] Daily minimum temperature
  [X] Daily maximum temperature - SELECTED
  [X] Relative humidity - SELECTED
  [ ] Atmospheric pressure
  [X] Wind speed - SELECTED
  
Selected: 15/29 fields
```

### 5. **Automatic Setup**
```
DATABASE SCHEMA MANAGEMENT
===========================
Checking and extending database schema...

Fields already present in database:
  ✓ dateTime - already exists, skipping
  ✓ interval - already exists, skipping

Adding missing fields to database:
  Adding field 'ow_temperature' (REAL)...
    ✓ Successfully added 'ow_temperature'
  Adding field 'ow_humidity' (REAL)...
    ✓ Successfully added 'ow_humidity'
  Adding field 'ow_weather_main' (VARCHAR(20))...
    ✓ Successfully added 'ow_weather_main' using direct SQL

✓ Database schema management completed successfully
  Fields already present: 2
  Fields created: 27

INSTALLATION COMPLETED SUCCESSFULLY!
====================================
✓ Files installed
✓ Service registered automatically: user.openweather.OpenWeatherService
✓ Interactive configuration completed
✓ Database schema extended
✓ Unit system configured
✓ Enhanced configuration written successfully
  - Unit system: US → OpenWeather imperial
  - Field mappings: 2 modules configured
  - Conversion specs: Yes
```

## ⚙️ Configuration

The installer automatically configures the extension with enhanced settings in `weewx.conf`:

```ini
[OpenWeatherService]
    enable = true
    api_key = YOUR_API_KEY_HERE
    timeout = 30
    log_success = false
    log_errors = true
    retry_attempts = 3
    
    [[field_selection]]
        selection_timestamp = 1753602647
        config_version = 1.0
        complexity_level = all
        [[[selected_fields]]]
            current_weather = temp, feels_like, temp_min, temp_max, humidity, pressure, sea_level, grnd_level, wind_speed, wind_direction, wind_gust, cloud_cover, visibility, rain_1h, rain_3h, snow_1h, snow_3h, weather_main, weather_description, weather_icon
            air_quality = pm2_5, pm10, ozone, no2, so2, co, nh3, no, aqi
    
    [[unit_system]]
        weewx_system = US
        api_units = imperial
        wind_conversion_needed = False
    
    [[api_modules]]
        [[[current_weather]]]
            api_url = http://api.openweathermap.org/data/2.5/weather
            interval = 3600
            units_parameter = True
        [[[air_quality]]]
            api_url = http://api.openweathermap.org/data/2.5/air_pollution
            interval = 7200
            units_parameter = False
    
    [[field_mappings]]
        # Complete field mapping data with unit conversions
        # (Full mappings auto-generated by installer)
    
    [[unit_conversions]]
        [[[wind_speed_m_s_to_km_h]]]
            description = Convert OpenWeather m/s to WeeWX METRIC km/hr
            formula = x * 3.6
```

## 📈 API Usage & Rate Limits

- **Free Tier**: 1,000 calls/day, 60 calls/minute
- **Default Configuration**: ~36 calls/day (well within limits)
- **Configurable Intervals**: Minimum 10 minutes recommended
- **Usage Estimation**: Automatic calculation during installation
- **Efficient Collection**: Module-based API calls only when needed

Example daily usage calculation:
- Current Weather: Every 60 minutes = 24 calls/day
- Air Quality: Every 120 minutes = 12 calls/day
- **Total**: 36 calls/day (3.6% of free tier)

## 🔧 Architecture & Reliability

### Automatic Service Management
- **Installation**: Service automatically registered via WeeWX 5.1 ExtensionInstaller
- **Uninstall**: Complete removal with `weectl extension uninstall OpenWeather`
- **No Manual Configuration**: Service registration handled automatically

### Enhanced Unit System Integration
- **Automatic Detection**: Reads WeeWX unit system from configuration
- **Smart API Calls**: Uses appropriate OpenWeather units parameter
- **Seamless Conversion**: Automatic wind speed conversion for METRIC systems
- **Data-Driven**: Unit groups and conversions from YAML configuration

### Thread-Safe Data Collection
- **Background Processing**: API calls in separate threads, non-blocking WeeWX
- **Thread Safety**: Proper locking mechanisms for shared data access
- **Graceful Shutdown**: Clean thread termination on WeeWX stop
- **Error Recovery**: Robust error handling with exponential backoff

### Database Integration
- **Dynamic Schema**: Database fields created only for selected data
- **Hybrid Field Creation**: Uses weectl for numeric types, direct SQL for VARCHAR
- **Type Safety**: Proper field types (REAL, INTEGER, VARCHAR)
- **Existing Field Detection**: Handles reinstallation gracefully
- **Cross-Platform**: Compatible with SQLite and MySQL

## 📊 Data Integration

### Database Fields
Fields are prefixed with `ow_` to avoid conflicts:

**Current Weather Fields (20 fields):**
- `ow_temperature` (REAL) - Current temperature
- `ow_feels_like` (REAL) - Feels-like temperature
- `ow_temp_min` (REAL) - Daily minimum temperature
- `ow_temp_max` (REAL) - Daily maximum temperature
- `ow_humidity` (REAL) - Relative humidity percentage
- `ow_pressure` (REAL) - Atmospheric pressure
- `ow_sea_level` (REAL) - Sea level pressure
- `ow_grnd_level` (REAL) - Ground level pressure
- `ow_wind_speed` (REAL) - Wind speed
- `ow_wind_direction` (REAL) - Wind direction in degrees
- `ow_wind_gust` (REAL) - Wind gusts
- `ow_cloud_cover` (REAL) - Cloud cover percentage
- `ow_visibility` (REAL) - Visibility in meters
- `ow_rain_1h` (REAL) - Rain in last hour
- `ow_rain_3h` (REAL) - Rain in last 3 hours
- `ow_snow_1h` (REAL) - Snow in last hour
- `ow_snow_3h` (REAL) - Snow in last 3 hours
- `ow_weather_main` (VARCHAR(20)) - Weather category
- `ow_weather_description` (VARCHAR(50)) - Weather description
- `ow_weather_icon` (VARCHAR(10)) - Weather icon code

**Air Quality Fields (9 fields):**
- `ow_aqi` (INTEGER) - Air Quality Index (1-5 scale)
- `ow_pm25` (REAL) - PM2.5 concentration
- `ow_pm10` (REAL) - PM10 concentration
- `ow_ozone` (REAL) - Ozone concentration
- `ow_no2` (REAL) - Nitrogen dioxide concentration
- `ow_so2` (REAL) - Sulfur dioxide concentration
- `ow_co` (REAL) - Carbon monoxide concentration
- `ow_nh3` (REAL) - Ammonia concentration
- `ow_no` (REAL) - Nitrogen monoxide concentration

### Report Integration

You can create custom reports using the new fields:

```html
<!-- In your skin templates -->
<p>Current Temperature: $current.ow_temperature°F</p>
<p>Feels Like: $current.ow_feels_like°F</p>
<p>Weather: $current.ow_weather_description</p>
<p>Air Quality Index: $current.ow_aqi</p>
<p>PM2.5 Level: $current.ow_pm25 μg/m³</p>

<!-- Historical data -->
<p>Today's Max Temperature: $day.ow_temp_max.max</p>
<p>This Week's Average AQI: $week.ow_aqi.avg</p>
```

### Database Queries

Access data directly from the database:

```sql
-- Recent readings with OpenWeather data
SELECT datetime(dateTime, 'unixepoch', 'localtime') as date,
       outTemp, ow_temperature, ow_feels_like, ow_weather_main, 
       ow_aqi, ow_pm25
FROM archive 
WHERE ow_temperature IS NOT NULL 
ORDER BY dateTime DESC 
LIMIT 24;

-- Daily averages with weather conditions
SELECT date(datetime(dateTime, 'unixepoch', 'localtime')) as date,
       ROUND(AVG(ow_temperature), 1) as avg_temp,
       ROUND(AVG(ow_aqi), 1) as avg_aqi,
       ow_weather_main as weather_condition
FROM archive 
WHERE ow_temperature IS NOT NULL 
GROUP BY date 
ORDER BY date DESC;
```

## 🧪 Testing and Validation

The extension includes comprehensive built-in testing tools:

```bash
# Test all components
python3 /etc/weewx/bin/user/openweather.py --test-all

# Test installation (database + service registration)
python3 /etc/weewx/bin/user/openweather.py --test-install

# Test API connectivity (requires API key)
python3 /etc/weewx/bin/user/openweather.py --test-api --api-key=YOUR_KEY

# Test specific components
python3 /etc/weewx/bin/user/openweather.py --test-data
python3 /etc/weewx/bin/user/openweather.py --test-config
python3 /etc/weewx/bin/user/openweather.py --test-database
python3 /etc/weewx/bin/user/openweather.py --test-registration
python3 /etc/weewx/bin/user/openweather.py --test-service
python3 /etc/weewx/bin/user/openweather.py --test-fields

# Show extension information
python3 /etc/weewx/bin/user/openweather.py --info
python3 /etc/weewx/bin/user/openweather.py --version
```

### Built-in Test Suite Features:
- **API Connectivity**: Tests all OpenWeather API endpoints
- **Data Processing**: Validates field extraction and mapping
- **Field Selection**: Tests complexity levels and custom selection
- **Configuration**: Validates WeeWX integration settings
- **Database Schema**: Checks field creation and data presence
- **Service Registration**: Verifies WeeWX service integration
- **Thread Safety**: Tests concurrent data access patterns
- **Unit System**: Validates unit conversion functionality

### Test Output Example:
```
🧪 RUNNING ALL TESTS
============================================================
✅ API Connectivity: 2/2 APIs working
✅ Field Selection: 29 fields correctly managed
✅ Data Processing: Field extraction working
✅ Configuration: WeeWX integration valid
✅ Database Schema: 29 OpenWeather fields present
✅ Service Registration: user.openweather.OpenWeatherService found
✅ Service Integration: Unit mappings correct
✅ Thread Safety: No threading errors

TEST SUMMARY: 8/8 tests passed
🎉 ALL TESTS PASSED! Extension is working correctly.
```

## 🔄 Upgrade and Maintenance

### Updating the Extension

```bash
# Download new version
wget https://github.com/inguy24/weewx-openweather_API/releases/latest/download/weewx-openweather.zip

# Reinstall (preserves configuration and database fields)
weectl extension install weewx-openweather.zip

# Restart WeeWX
sudo systemctl restart weewx
```

### Reconfiguring Field Selection

```bash
# Change field selection without reinstalling
weectl extension reconfigure OpenWeather

# This will:
# - Keep existing data
# - Add new fields if selected
# - Update configuration
# - Preserve API key and settings
```

### API Key Management

OpenWeatherMap API keys are permanent but you can regenerate them:

1. Visit [OpenWeatherMap API Keys](https://home.openweathermap.org/api_keys)
2. Generate new key if needed
3. Update `weewx.conf` with new key:
   ```ini
   [OpenWeatherService]
       api_key = YOUR_NEW_API_KEY
   ```
4. Restart WeeWX

## 🗑️ Uninstallation

```bash
# Remove the extension completely
weectl extension uninstall OpenWeather

# Restart WeeWX
sudo systemctl restart weewx
```

**Note**: Uninstallation removes the service and configuration but preserves your collected data in the database.

## 🛠️ Troubleshooting

### Common Issues

**Installation Problems:**
- Ensure WeeWX 5.1+ is installed: `weectl --version`
- Check Python version: `python3 --version` (3.7+ required)
- Verify internet connectivity for API key validation

**API Issues:**
- **Invalid API Key**: Verify key is correct and active (10+ minutes after creation)
- **Rate Limiting**: Check API usage at OpenWeatherMap dashboard
- **Network Errors**: Check firewall settings and internet connectivity

**Database Issues:**
- **Field Creation Errors**: Check WeeWX has write permissions to database
- **Missing Data**: Verify service is running in WeeWX logs
- **Field Conflicts**: Avoid reinstalling over modified database schemas

**Service Issues:**
- **Service Not Running**: Check service registration with built-in tests
- **Unit Conversion**: Verify unit system detection is correct
- **Data Collection**: Monitor thread activity in logs

### Log Monitoring

```bash
# Monitor WeeWX logs for OpenWeather activity
sudo journalctl -u weewx -f | grep -i openweather

# Check for successful data collection
sudo journalctl -u weewx -f | grep "OpenWeather.*collected"

# Monitor for errors
sudo journalctl -u weewx -f | grep -i "error\|fail"
```

### Debug Configuration

Enable detailed logging in `weewx.conf`:

```ini
[OpenWeatherService]
    log_success = true
    log_errors = true

[Logging]
    [[loggers]]
        [[[user.openweather]]]
            level = DEBUG
```

### Diagnostic Commands

```bash
# Run installation test
python3 /etc/weewx/bin/user/openweather.py --test-install

# Check service registration
python3 /etc/weewx/bin/user/openweather.py --test-registration

# Verify API connectivity
python3 /etc/weewx/bin/user/openweather.py --test-api --api-key=YOUR_KEY

# Test database schema
python3 /etc/weewx/bin/user/openweather.py --test-database
```

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Development Setup

```bash
# Clone the repository
git clone https://github.com/inguy24/weewx-openweather_API.git
cd weewx-openweather_API

# Install in development mode
weectl extension install .

# Run tests
python3 bin/user/openweather.py --test-all

# Test specific functionality
python3 bin/user/openweather.py --test-fields
```

## 🔮 Related Extensions (In Development)

**Note**: These companion extensions are currently in development and not yet available for installation.

### 🦠 WeeWX CDC Surveillance Extension (Coming Soon)
*Planned release: Q3 2025*
- Integrates CDC environmental health surveillance data
- Tracks disease outbreak patterns correlated with weather
- Provides public health alerts and recommendations
- Designed to work alongside OpenWeather data

### 🏥 WeeWX Environmental Health Extension (Coming Soon)  
*Planned release: Q3 2025*
- Comprehensive health risk assessment combining weather, air quality, and surveillance data
- Heat index health warnings and cold weather advisories
- Air quality health impact calculations
- Personalized health recommendations based on environmental conditions
- Advanced reporting with health trend analysis

**Stay Updated**: Watch this repository and check [Releases](https://github.com/inguy24/weewx-openweather_API/releases) for announcements about these upcoming extensions.

## 📄 License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.

Copyright (C) 2025 Shane Burkhardt - [GitHub Profile](https://github.com/inguy24)

## 🙏 Acknowledgments

- **WeeWX Community** - For the excellent weather station software
- **OpenWeatherMap** - For providing comprehensive weather and air quality APIs
- **Alpha Testers** - Community members helping test and improve this extension

## 📞 Support

- **Bug Reports**: [GitHub Issues](https://github.com/inguy24/weewx-openweather_API/issues)
- **Feature Requests**: [GitHub Issues](https://github.com/inguy24/weewx-openweather_API/issues) with enhancement label
- **Discussions**: [GitHub Discussions](https://github.com/inguy24/weewx-openweather_API/discussions)
- **WeeWX Help**: [WeeWX User Group](https://groups.google.com/g/weewx-user)

---

**Version**: 1.0.0 | **WeeWX Compatibility**: 5.1+ | **License**: GPL v3.0 | **Author**: [Shane Burkhardt](https://github.com/inguy24)
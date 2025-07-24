# WeeWX OpenWeather Extension

A comprehensive WeeWX extension that integrates OpenWeatherMap APIs to provide weather and air quality data with **interactive field selection** and efficient API usage.

## 🌟 Features

- **Interactive Field Selection**: Choose exactly which data fields you want during installation
- **Smart Complexity Levels**: 4 predefined levels from minimal (6 fields) to everything (20+ fields)
- **Custom Field Selection**: Advanced curses-based interface for precise field control
- **Dynamic Database Schema**: Only creates database fields for selected data
- **Current Weather Data**: Temperature, humidity, pressure, wind, cloud cover, visibility
- **Air Quality Data**: PM2.5, PM10, O₃, NO₂, SO₂, CO, NH₃, OpenWeather AQI (1-5 scale)
- **UV Index**: Current UV radiation data (framework ready)
- **Forecast Data**: Daily and hourly forecasts (framework ready)
- **Modular Configuration**: Enable only the data modules you need
- **Rate Limit Management**: Efficient API usage with configurable intervals
- **Multi-Source Support**: Works alongside local weather stations  
- **Thread-Safe Operation**: Non-blocking background data collection
- **Robust Installation**: Automatic service registration and clean uninstall

## 📊 Field Selection System

### Complexity Levels

| Level | Fields | Description |
|-------|--------|-------------|
| **Minimal** | 6 fields | Temperature, humidity, pressure, wind speed, PM2.5, AQI |
| **Standard** | 9 fields | All minimal + feels-like temp, wind direction, cloud cover |
| **Comprehensive** | 16 fields | All standard + visibility, wind gusts, daily min/max temp, PM10, ozone, NO2 |
| **Everything** | 20+ fields | All available fields including rain/snow, atmospheric details, weather descriptions, all gases |
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
# 2. Module selection (current_weather, air_quality)
# 3. Field selection (complexity level or custom)
# 4. Automatic database schema creation
# 5. Service registration

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

### 2. **Module Selection**
```
MODULE SELECTION
================
Choose which OpenWeather data modules to enable:

Enable current weather data (temperature, humidity, pressure, wind)? [Y/n]: Y
✓ Current weather module enabled

Enable air quality data (PM2.5, ozone, AQI)? [Y/n]: Y
✓ Air quality module enabled
```

### 3. **Field Selection**
```
OPENWEATHER DATA COLLECTION LEVEL
==================================

Choose data collection level:
1. Minimal
   Fields: Temperature, humidity, pressure, wind speed, PM2.5, AQI

2. Standard
   Fields: Temperature, feels-like, humidity, pressure, wind speed & direction, cloud cover, PM2.5, AQI

3. Comprehensive
   Fields: All standard plus: visibility, wind gusts, daily min/max temp, PM10, ozone, NO2

4. Everything
   Fields: All 20+ fields including rain/snow data, atmospheric details, weather descriptions, and all air quality gases

5. Custom
   Choose specific fields manually

Enter choice [1-5]: 2
✓ Selected: Standard
```

### 4. **Custom Field Selection** (if option 5 chosen)
Interactive curses-based interface for precise field control:
```
CUSTOM FIELD SELECTION - Select All Desired Fields
===================================================
↑↓:Navigate  SPACE:Toggle  ENTER:Confirm  q:Quit

=== CURRENT WEATHER ===
  Temperature:
    → [ ] Current temperature (x/n): x
    ✓ [X] Current temperature - SELECTED
      [ ] Feels-like temperature (x/n): n
      [ ] Feels-like temperature - skipped
      
  Atmospheric:
    → [ ] Atmospheric pressure (x/n): x
    ✓ [X] Atmospheric pressure - SELECTED
    
Selected: 8 total | Current Weather: 5 | Air Quality: 3
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

✓ Database schema management completed successfully
  Fields already present: 2
  Fields created: 8

INSTALLATION COMPLETED SUCCESSFULLY!
====================================
✓ API key configured
✓ Data collection level: Standard
✓ Database fields created: 8
✓ Service registration: Automatic via ExtensionInstaller
✓ Unit system configured
```

## ⚙️ Configuration

The installer automatically configures the extension, but you can customize settings in `weewx.conf`:

```ini
[OpenWeatherService]
    enable = true
    api_key = YOUR_API_KEY_HERE
    timeout = 30
    log_success = false
    log_errors = true
    
    [[modules]]
        current_weather = true
        air_quality = true
    
    [[intervals]]
        current_weather = 3600
        air_quality = 7200
    
    [[field_selection]]
        complexity_level = standard
        [[[current_weather]]]
            temp = true
            feels_like = true
            humidity = true
            pressure = true
            wind_speed = true
            wind_direction = true
            cloud_cover = true
        [[[air_quality]]]
            pm2_5 = true
            aqi = true
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

### Thread-Safe Data Collection
- **Background Processing**: API calls in separate threads, non-blocking WeeWX
- **Thread Safety**: Proper locking mechanisms for shared data access
- **Graceful Shutdown**: Clean thread termination on WeeWX stop
- **Error Recovery**: Robust error handling with exponential backoff

### Database Integration
- **Dynamic Schema**: Database fields created only for selected data
- **Type Safety**: Proper field types (REAL, INTEGER, TEXT)
- **Existing Field Detection**: Handles reinstallation gracefully
- **Cross-Platform**: Compatible with SQLite and MySQL

## 📊 Data Integration

### Database Fields
Fields are prefixed with `ow_` to avoid conflicts:

**Current Weather Fields:**
- `ow_temperature` (REAL) - Current temperature
- `ow_feels_like` (REAL) - Feels-like temperature
- `ow_humidity` (REAL) - Relative humidity percentage
- `ow_pressure` (REAL) - Atmospheric pressure
- `ow_wind_speed` (REAL) - Wind speed
- `ow_wind_direction` (INTEGER) - Wind direction in degrees
- `ow_cloud_cover` (INTEGER) - Cloud cover percentage
- `ow_visibility` (INTEGER) - Visibility in meters

**Air Quality Fields:**
- `ow_aqi` (INTEGER) - Air Quality Index (1-5 scale)
- `ow_pm2_5` (REAL) - PM2.5 concentration
- `ow_pm10` (REAL) - PM10 concentration
- `ow_ozone` (REAL) - Ozone concentration
- `ow_no2` (REAL) - Nitrogen dioxide concentration
- `ow_so2` (REAL) - Sulfur dioxide concentration
- `ow_co` (REAL) - Carbon monoxide concentration
- `ow_nh3` (REAL) - Ammonia concentration

### Report Integration

You can create custom reports using the new fields:

```html
<!-- In your skin templates -->
<p>Current Temperature: $current.ow_temperature°F</p>
<p>Air Quality Index: $current.ow_aqi</p>
<p>PM2.5 Level: $current.ow_pm2_5 μg/m³</p>

<!-- Historical data -->
<p>Today's Max Temperature: $day.ow_temperature.max</p>
<p>This Week's Average AQI: $week.ow_aqi.avg</p>
```

### Database Queries

Access data directly from the database:

```sql
-- Recent readings with OpenWeather data
SELECT datetime(dateTime, 'unixepoch', 'localtime') as date,
       outTemp, ow_temperature, ow_feels_like, ow_aqi, ow_pm2_5
FROM archive 
WHERE ow_temperature IS NOT NULL 
ORDER BY dateTime DESC 
LIMIT 24;

-- Daily averages
SELECT date(datetime(dateTime, 'unixepoch', 'localtime')) as date,
       ROUND(AVG(ow_temperature), 1) as avg_temp,
       ROUND(AVG(ow_aqi), 1) as avg_aqi
FROM archive 
WHERE ow_temperature IS NOT NULL 
GROUP BY date 
ORDER BY date DESC;
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

## 🧪 Testing and Validation

The extension includes comprehensive testing tools:

```bash
# Test installation and database schema
python3 /etc/weewx/bin/user/openweather.py --test-install

# Test API connectivity
python3 /etc/weewx/bin/user/openweather.py --test-api --api-key=YOUR_KEY

# Test all components
python3 /etc/weewx/bin/user/openweather.py --test-all

# Show extension information
python3 /etc/weewx/bin/user/openweather.py --info
```

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
python3 examples/run_all_tests.py

# Test specific functionality
python3 bin/user/openweather.py --test-all
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

**Version**: 1.0.0 | **WeeWX Compatibility**: 5.1+ | **License**: GPL v3.0
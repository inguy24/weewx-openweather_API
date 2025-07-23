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
- PyYAML library (automatically installed)

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

### 5. **Database Schema Creation**
```
DATABASE SCHEMA MANAGEMENT
===========================
Checking and extending database schema...

Adding missing fields to database:
  Adding field 'ow_temperature' (REAL)...
    ✓ Successfully added 'ow_temperature'
  Adding field 'ow_pm25' (REAL)...
    ✓ Successfully added 'ow_pm25'
  [additional fields based on selection...]

✓ Database schema management completed successfully
```

### 6. **Installation Complete**
```
INSTALLATION COMPLETED SUCCESSFULLY!
====================================
✓ API key configured
✓ Data collection level: Standard
✓ Database fields created: 9
✓ Service registered: user.openweather.OpenWeatherService
✓ Unit system configured

Next steps:
1. Restart WeeWX: sudo systemctl restart weewx
2. Check logs: sudo journalctl -u weewx -f
3. Verify data collection in database/reports
```

## ⚙️ Configuration

### Automatic Configuration Created
The installer creates this configuration based on your selections:

```ini
[OpenWeatherService]
    enable = true
    api_key = YOUR_API_KEY_HERE
    log_success = false
    log_errors = true
    timeout = 30
    
    # Modules enabled during installation
    [[modules]]
        current_weather = true
        air_quality = true
    
    # API call intervals
    [[intervals]]
        current_weather = 3600    # 1 hour
        air_quality = 7200        # 2 hours
    
    # Field selection (created automatically)
    [[field_selection]]
        complexity_level = "standard"  # or "custom" for manual selection
        
        # Custom selections (only used if complexity_level = "custom")
        [[[current_weather]]]
            temp = true
            feels_like = true
            humidity = true
            pressure = true
            wind_speed = true
            wind_direction = true
            cloud_cover = true
            # Only selected fields = true
        
        [[[air_quality]]]
            pm2_5 = true
            aqi = true
            # Only selected fields = true

# Service automatically registered
[Engine]
    [[Services]]
        data_services = user.openweather.OpenWeatherService, weewx.engine.StdConvert, weewx.engine.StdCalibrate, weewx.engine.StdQC
```

### Manual Configuration (Optional)
You can modify settings after installation:

```ini
[OpenWeatherService]
    # Change complexity level
    [[field_selection]]
        complexity_level = "comprehensive"  # minimal/standard/comprehensive/everything
        
    # Or enable custom selection and modify fields
    [[field_selection]]
        complexity_level = "custom"
        [[[current_weather]]]
            temp = true
            feels_like = false
            temp_min = true
            temp_max = true
            # ... modify as needed
```

## 📋 Database Fields

Fields are created dynamically based on your selection. All fields use the `ow_` prefix:

### Current Weather Module (Available Fields)
- `ow_temperature` (°C) - Current temperature
- `ow_feels_like` (°C) - Feels like temperature  
- `ow_temp_min` (°C) - Daily minimum temperature
- `ow_temp_max` (°C) - Daily maximum temperature
- `ow_pressure` (hPa) - Atmospheric pressure
- `ow_humidity` (%) - Relative humidity
- `ow_sea_level` (hPa) - Sea level pressure
- `ow_grnd_level` (hPa) - Ground level pressure
- `ow_cloud_cover` (%) - Cloud cover percentage (0-100%)
- `ow_visibility` (m) - Visibility distance
- `ow_wind_speed` (m/s) - Wind speed
- `ow_wind_direction` (°) - Wind direction (degrees)
- `ow_wind_gust` (m/s) - Wind gusts
- `ow_rain_1h` (mm) - Rain last hour
- `ow_rain_3h` (mm) - Rain last 3 hours
- `ow_snow_1h` (mm) - Snow last hour
- `ow_snow_3h` (mm) - Snow last 3 hours
- `ow_weather_main` (text) - Weather category
- `ow_weather_description` (text) - Weather description
- `ow_weather_icon` (text) - Weather icon code

### Air Quality Module (Available Fields)
- `ow_pm25` (μg/m³) - PM2.5 concentration
- `ow_pm10` (μg/m³) - PM10 concentration
- `ow_ozone` (μg/m³) - Ozone concentration
- `ow_no2` (μg/m³) - NO₂ concentration
- `ow_so2` (μg/m³) - SO₂ concentration
- `ow_co` (μg/m³) - CO concentration
- `ow_nh3` (μg/m³) - NH₃ concentration
- `ow_no` (μg/m³) - NO concentration
- `ow_aqi` (1-5) - OpenWeather AQI (European scale)

### Example Field Selection Results

| Complexity Level | Database Fields Created | Example Fields |
|------------------|------------------------|----------------|
| **Minimal** | 6 fields | `ow_temperature`, `ow_humidity`, `ow_pressure`, `ow_wind_speed`, `ow_pm25`, `ow_aqi` |
| **Standard** | 9 fields | All minimal + `ow_feels_like`, `ow_wind_direction`, `ow_cloud_cover` |
| **Comprehensive** | 16 fields | All standard + `ow_visibility`, `ow_wind_gust`, `ow_temp_min`, `ow_temp_max`, `ow_pm10`, `ow_ozone`, `ow_no2` |

## 🔄 Changing Field Selection After Installation

### Method 1: Reinstall with New Selection
```bash
# Reinstall to change field selection
weectl extension install weewx-openweather.zip

# Choose different complexity level or custom fields
# Existing fields are preserved, new ones added as needed
```

### Method 2: Manual Configuration Edit
```bash
# Edit weewx.conf
sudo nano /etc/weewx/weewx.conf

# Change complexity_level or modify custom field selections
[OpenWeatherService]
    [[field_selection]]
        complexity_level = "comprehensive"  # Change level

# Add new database fields manually if switching to higher complexity
weectl database add-column ow_visibility --type REAL -y
weectl database add-column ow_wind_gust --type REAL -y

# Restart WeeWX
sudo systemctl restart weewx
```

## 📊 API Usage and Rate Limits

### Free Tier Limits
- **Daily**: 1,000 calls/day
- **Per minute**: 60 calls/minute
- **Geographic**: Global coverage

### Usage Based on Field Selection
API usage is the same regardless of field selection - efficiency comes from reduced processing and database storage.

| Module | Default Interval | Daily Calls |
|--------|------------------|-------------|
| Current Weather | 1 hour | 24 |
| Air Quality | 2 hours | 12 |
| **Total** | | **36 calls/day** |

Well within the 1,000 call daily limit!

## 🔧 Troubleshooting

### Field Selection Issues

**"No fields selected" during custom selection**
```bash
# Falls back to 'standard' defaults automatically
# Check logs: sudo journalctl -u weewx -f
```

**Database fields not created**
```bash
# Check field creation in logs
grep "database" /var/log/weewx/weewx.log

# Manually add missing fields
weectl database add-column ow_temperature --type REAL -y
weectl database add-column ow_pm25 --type REAL -y
```

**Custom selection interface not working**
```bash
# Falls back to terminal prompts if curses unavailable
# Standard field selection will be used
```

### Configuration Issues

**Invalid complexity level**
```bash
# Edit weewx.conf and set to valid level
[OpenWeatherService]
    [[field_selection]]
        complexity_level = "standard"  # minimal/standard/comprehensive/everything
```

**Field selection mismatch**
```bash
# Check which fields are actually in database
weectl database show

# Compare with configuration
grep -A 20 "field_selection" /etc/weewx/weewx.conf
```

### Standard Troubleshooting

**API Key Errors**
- Verify key at https://openweathermap.org/api
- Check that key is active (may take 10 minutes)
- Ensure no extra spaces in configuration

**No Data in Database**
- Check WeeWX logs: `sudo tail -f /var/log/weewx/weewx.log`
- Verify field selection in configuration
- Check API connectivity

**Rate Limit Exceeded**
- Increase intervals in configuration
- Monitor usage: `grep "OpenWeather" /var/log/weewx/weewx.log | wc -l`

## 📖 Examples

### Using Selected Fields in Templates
```html
<!-- Only works if fields were selected during installation -->
<p>Current Temperature: $current.ow_temperature</p>
<p>Air Quality Index: $current.ow_aqi</p>

<!-- Check if field exists before using -->
#if $current.ow_feels_like is not None
<p>Feels Like: $current.ow_feels_like</p>
#end if
```

### Database Queries
```sql
-- Query only selected fields (example for 'standard' selection)
SELECT datetime(dateTime, 'unixepoch', 'localtime') as date,
       ow_temperature, ow_feels_like, ow_humidity, 
       ow_pressure, ow_wind_speed, ow_wind_direction,
       ow_cloud_cover, ow_pm25, ow_aqi
FROM archive 
WHERE ow_temperature IS NOT NULL 
ORDER BY dateTime DESC 
LIMIT 10;
```

## 🚀 Advanced Usage

### Upgrading Field Selection
```bash
# To add more fields later:
# 1. Reinstall with higher complexity level
weectl extension install weewx-openweather.zip

# 2. Select "comprehensive" or "everything"
# 3. Existing data preserved, new fields added
```

### Performance Optimization
- **Minimal Selection**: Fastest performance, smallest database
- **Standard Selection**: Good balance of data and performance  
- **Custom Selection**: Optimize for your specific needs
- **Everything**: Maximum data, larger database size

## 🤝 Contributing

Contributions welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Field Selection Development
- Field definitions: `openweather_fields.yaml`
- Smart defaults: `field_selection_defaults.yaml`
- Interactive UI: `install.py` (TerminalUI class)

## 📄 License

GNU General Public License v3.0 - see [LICENSE](LICENSE) file for details.

## 🔗 Related Extensions

This extension is designed to work with:
- **WeeWX CDC Surveillance Extension**: Public health surveillance data
- **WeeWX Environmental Health Extension**: Combined health risk assessment

## 📞 Support

- **Documentation**: This README and inline code comments
- **Issues**: [GitHub Issues](https://github.com/inguy24/weewx-openweather_API/issues)
- **WeeWX Forum**: [WeeWX User Group](https://groups.google.com/g/weewx-user)

---

**Enhanced with smart field selection for efficient, customized weather data collection.**
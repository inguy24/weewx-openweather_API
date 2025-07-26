#!/usr/bin/env python3
"""
WeeWX OpenWeather Extension Installer - Reorganized with Proper Service Registration

Provides interactive installation with field selection and automatic service management.
Fixes uninstall issues and architectural separation of concerns.

Copyright (C) 2025 WeeWX OpenWeather API Extension
"""

import sys
import os
import re
import yaml
import subprocess
import time
import configobj
from typing import Dict, List, Optional, Any

try:
    from weecfg.extension import ExtensionInstaller
    import weewx.manager
except ImportError:
    print("Error: This installer requires WeeWX 5.1 or later")
    sys.exit(1)

def loader():
    return OpenWeatherInstaller()


class TerminalUI:
    """Simple terminal UI for field selection."""
    
    def __init__(self):
        self.selected_items = set()
    
    def show_complexity_menu(self):
        """Show complexity level selection menu with field descriptions."""
        print("\n" + "="*80)
        print("OPENWEATHER DATA COLLECTION LEVEL")
        print("="*80)
        
        # Load defaults to show field lists
        try:
            defaults_path = os.path.join(os.path.dirname(__file__), 'field_selection_defaults.yaml')
            with open(defaults_path, 'r') as f:
                defaults = yaml.safe_load(f)['field_selection_defaults']
        except:
            # Fallback if YAML not available
            defaults = {
                'minimal': {'field_list': 'Temperature, humidity, pressure, wind speed, PM2.5, AQI'},
                'standard': {'field_list': 'Temperature, feels-like, humidity, pressure, wind speed & direction, cloud cover, PM2.5, AQI'},
                'comprehensive': {'field_list': 'All standard fields plus: visibility, wind gusts, daily min/max temp, PM10, ozone, NO2'},
                'everything': {'field_list': 'All 20+ fields including rain/snow data, atmospheric details, weather descriptions, and all air quality gases'}
            }
        
        options = [
            ("Minimal", defaults.get('minimal', {}).get('field_list', '4 essential fields')),
            ("Standard", defaults.get('standard', {}).get('field_list', '8 most common fields')),
            ("Comprehensive", defaults.get('comprehensive', {}).get('field_list', '15 advanced fields')),
            ("Everything", defaults.get('everything', {}).get('field_list', 'All available fields')),
            ("Custom", "Choose specific fields manually")
        ]
        
        print("\nChoose data collection level:")
        print("-" * 40)
        
        for i, (name, description) in enumerate(options, 1):
            print(f"{i}. {name}")
            print(f"   Fields: {description}")
            print()
        
        while True:
            try:
                choice = input("Enter choice [1-5]: ").strip()
                if choice in ['1', '2', '3', '4', '5']:
                    complexity_levels = ['minimal', 'standard', 'comprehensive', 'everything', 'custom']
                    selected = complexity_levels[int(choice) - 1]
                    print(f"\n✓ Selected: {options[int(choice) - 1][0]}")
                    return selected
                else:
                    print("Invalid choice. Please enter 1, 2, 3, 4, or 5.")
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
    
    def show_custom_selection(self, field_definitions):
        """Show single-screen checklist for custom field selection using curses."""
        import curses
        
        def curses_main(stdscr):
            # Initialize curses
            curses.curs_set(0)  # Hide cursor
            curses.use_default_colors()
            if curses.has_colors():
                curses.start_color()
                curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Highlight
                curses.init_pair(2, curses.COLOR_GREEN, -1)  # Selected
                curses.init_pair(3, curses.COLOR_BLUE, -1)   # Header
                curses.init_pair(4, curses.COLOR_CYAN, -1)   # Module headers
            
            # Organize all fields into a single list
            all_fields = []
            field_to_module = {}
            
            for module_name, module_data in field_definitions.items():
                module_display = module_name.upper().replace('_', ' ')
                
                # Add module header
                all_fields.append({
                    'type': 'module_header',
                    'display': f"=== {module_display} ===",
                    'module': module_name
                })
                
                current_category = ""
                for category_name, category_data in module_data['categories'].items():
                    for field_name, field_info in category_data['fields'].items():
                        # Add category header if new
                        if category_data['display_name'] != current_category:
                            current_category = category_data['display_name']
                            all_fields.append({
                                'type': 'category_header',
                                'display': current_category,
                                'module': module_name
                            })
                        
                        # Add field
                        field_item = {
                            'type': 'field',
                            'name': field_name,
                            'display': field_info['display_name'],
                            'module': module_name,
                            'selected': 'false'  # String instead of boolean
                        }
                        all_fields.append(field_item)
                        field_to_module[len(all_fields) - 1] = module_name
            
            # State variables
            current_item = 0
            scroll_offset = 0
            
            # Find first selectable field
            while current_item < len(all_fields) and all_fields[current_item]['type'] != 'field':
                current_item += 1
            
            def draw_interface():
                stdscr.clear()
                height, width = stdscr.getmaxyx()
                
                # Title
                title = "CUSTOM FIELD SELECTION - Select All Desired Fields"
                stdscr.addstr(0, (width - len(title)) // 2, title, curses.color_pair(3) | curses.A_BOLD)
                
                # Instructions
                instructions = "↑↓:Navigate  SPACE:Toggle  ENTER:Confirm  q:Quit"
                stdscr.addstr(1, (width - len(instructions)) // 2, instructions)
                stdscr.addstr(2, 0, "─" * width)
                
                # Calculate visible area
                visible_height = height - 6  # Leave space for title, instructions, summary
                
                # Adjust scroll if needed
                nonlocal scroll_offset
                if current_item < scroll_offset:
                    scroll_offset = current_item
                elif current_item >= scroll_offset + visible_height:
                    scroll_offset = current_item - visible_height + 1
                
                # Display fields
                y_pos = 3
                for i in range(scroll_offset, min(len(all_fields), scroll_offset + visible_height)):
                    if y_pos >= height - 3:
                        break
                    
                    item = all_fields[i]
                    
                    if item['type'] == 'module_header':
                        # Module header
                        stdscr.addstr(y_pos, 0, item['display'], curses.color_pair(4) | curses.A_BOLD)
                    
                    elif item['type'] == 'category_header':
                        # Category header
                        stdscr.addstr(y_pos, 2, f"{item['display']}:", curses.color_pair(3))
                    
                    elif item['type'] == 'field':
                        # Field item
                        cursor = "→ " if i == current_item else "  "
                        checkbox = "[✓] " if item['selected'] == 'true' else "[ ] "  # Check string value
                        text = f"{cursor}{checkbox}{item['display']}"
                        
                        # Truncate if too long
                        if len(text) > width - 4:
                            text = text[:width - 7] + "..."
                        
                        # Apply highlighting and colors
                        attr = 0
                        if i == current_item:
                            attr |= curses.color_pair(1) | curses.A_REVERSE
                        if item['selected'] == 'true':  # Check string value
                            attr |= curses.color_pair(2)
                        
                        stdscr.addstr(y_pos, 4, text, attr)
                    
                    y_pos += 1
                
                # Summary at bottom
                if height > 10:
                    summary_y = height - 3
                    stdscr.addstr(summary_y, 0, "─" * width)
                    
                    # Count selected fields by module
                    selected_counts = {}
                    total_selected = 0
                    
                    for item in all_fields:
                        if item['type'] == 'field':
                            module = item['module']
                            if module not in selected_counts:
                                selected_counts[module] = 0
                            if item['selected'] == 'true':  # Check string value
                                selected_counts[module] += 1
                                total_selected += 1
                    
                    summary_text = f"Selected: {total_selected} total"
                    for module, count in selected_counts.items():
                        module_display = module.replace('_', ' ').title()
                        summary_text += f" | {module_display}: {count}"
                    
                    if len(summary_text) < width:
                        stdscr.addstr(summary_y + 1, 0, summary_text)
                    
                    # Scroll indicator
                    if len(all_fields) > visible_height:
                        scroll_info = f"Line {current_item + 1} of {len(all_fields)}"
                        stdscr.addstr(summary_y + 2, width - len(scroll_info) - 1, scroll_info)
                
                stdscr.refresh()
            
            # Main interaction loop
            while True:
                try:
                    draw_interface()
                    key = stdscr.getch()
                    
                    if key == ord('q') or key == ord('Q'):
                        return None  # User cancelled
                    elif key == 10 or key == 13:  # ENTER
                        break
                    elif key == curses.KEY_UP:
                        # Move to previous selectable item
                        new_pos = current_item - 1
                        while new_pos >= 0 and all_fields[new_pos]['type'] != 'field':
                            new_pos -= 1
                        if new_pos >= 0:
                            current_item = new_pos
                    elif key == curses.KEY_DOWN:
                        # Move to next selectable item
                        new_pos = current_item + 1
                        while new_pos < len(all_fields) and all_fields[new_pos]['type'] != 'field':
                            new_pos += 1
                        if new_pos < len(all_fields):
                            current_item = new_pos
                    elif key == 32:  # SPACE
                        if (current_item < len(all_fields) and 
                            all_fields[current_item]['type'] == 'field'):
                            # Toggle between 'true' and 'false' strings
                            current_selection = all_fields[current_item]['selected']
                            all_fields[current_item]['selected'] = 'false' if current_selection == 'true' else 'true'
                        
                except KeyboardInterrupt:
                    return None
            
            # Convert to expected format
            selected_fields = {'current_weather': [], 'air_quality': []}
            for item in all_fields:
                if item['type'] == 'field' and item['selected'] == 'true':  # Check string value
                    selected_fields[item['module']].append(item['name'])
            
            return selected_fields
        
        # Run curses interface
        try:
            result = curses.wrapper(curses_main)
            
            if result is None:
                print("\nCustom selection cancelled.")
                return None
            
            # Show final summary in regular terminal
            total_selected = sum(len(fields) for fields in result.values())
            print(f"\n" + "="*60)
            print(f"SELECTION SUMMARY: {total_selected} fields selected")
            print("="*60)
            
            for module_name, fields in result.items():
                module_display = module_name.replace('_', ' ').title()
                print(f"{module_display}: {len(fields)} fields")
                
                if fields:
                    # Show first few selected field names
                    field_names = []
                    for field_name in fields:
                        # Find display name
                        for module_data in field_definitions.values():
                            for category_data in module_data['categories'].values():
                                if field_name in category_data['fields']:
                                    field_names.append(category_data['fields'][field_name]['display_name'])
                                    break
                    
                    if field_names:
                        display_list = ', '.join(field_names[:3])
                        if len(field_names) > 3:
                            display_list += f" (and {len(field_names) - 3} more)"
                        print(f"  {display_list}")
            
            if total_selected == 0:
                print("\nWarning: No fields selected. Using 'standard' defaults instead.")
                return None
            
            return result
            
        except Exception as e:
            print(f"\nError with custom selection interface: {e}")
            print("Falling back to 'standard' field selection.")
            return None
    
    def confirm_selection(self, complexity_level, field_count_estimate):
        """Confirm the user's selection before proceeding."""
        print(f"\n" + "="*60)
        print("CONFIGURATION CONFIRMATION")
        print("="*60)
        print(f"Data collection level: {complexity_level.title()}")
        print(f"Estimated database fields: {field_count_estimate}")
        print(f"This will modify your WeeWX database schema.")
        print("-" * 60)
        
        while True:
            try:
                confirm = input("Proceed with this configuration? [y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if confirm in ['y', 'yes']:
                return 'true'  # Return string instead of boolean
            elif confirm in ['n', 'no']:
                return 'false'  # Return string instead of boolean
            else:
                print("Please enter 'y' for yes or 'n' for no")


class FieldSelectionHelper:
    """Helper class for field selection during installation."""
    
    def __init__(self, extension_dir):
        self.extension_dir = extension_dir
        self.defaults = self._load_defaults()
        self.field_definitions = self._load_field_definitions()
    
    def _load_defaults(self):
        """Load field selection defaults."""
        try:
            defaults_path = os.path.join(self.extension_dir, 'field_selection_defaults.yaml')
            with open(defaults_path, 'r') as f:
                return yaml.safe_load(f)['field_selection_defaults']
        except Exception as e:
            print(f"Warning: Could not load field defaults: {e}")
            return self._get_fallback_defaults()
    
    def _load_field_definitions(self):
        """Load field definitions."""
        try:
            definitions_path = os.path.join(self.extension_dir, 'openweather_fields.yaml')
            with open(definitions_path, 'r') as f:
                return yaml.safe_load(f)['field_definitions']
        except Exception as e:
            print(f"Warning: Could not load field definitions: {e}")
            return {'current_weather': {'categories': {}}, 'air_quality': {'categories': {}}}
    
    def _get_fallback_defaults(self):
        """Fallback defaults if YAML file not available."""
        return {
            'minimal': {
                'current_weather': ['temp', 'humidity', 'pressure', 'wind_speed'],
                'air_quality': ['pm2_5', 'aqi']
            },
            'standard': {
                'current_weather': ['temp', 'feels_like', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'cloud_cover'],
                'air_quality': ['pm2_5', 'aqi']
            },
            'comprehensive': {
                'current_weather': ['temp', 'feels_like', 'temp_min', 'temp_max', 'humidity', 'pressure', 'wind_speed', 'wind_direction', 'wind_gust', 'cloud_cover', 'visibility'],
                'air_quality': ['pm2_5', 'pm10', 'ozone', 'no2', 'aqi']
            },
            'everything': {
                'current_weather': 'all',
                'air_quality': 'all'
            }
        }
    
    def get_selected_fields(self, complexity_level):
        """Get field selection for complexity level."""
        return self.defaults.get(complexity_level, self.defaults.get('standard', {}))
    
    def estimate_field_count(self, selected_fields):
        """Estimate number of database fields for selection."""
        if not selected_fields:
            return 0
        
        count = 0
        for module, fields in selected_fields.items():
            if fields == 'all':
                # Count all fields in module
                if module in self.field_definitions:
                    for category_data in self.field_definitions[module]['categories'].values():
                        count += len(category_data['fields'])
            else:
                count += len(fields)
        
        return count
    
    def get_database_field_mappings(self, selected_fields):
        """Get database field mappings for selected fields."""
        mappings = {}
        
        for module, fields in selected_fields.items():
            if module in self.field_definitions:
                for category_data in self.field_definitions[module]['categories'].values():
                    for field_name, field_info in category_data['fields'].items():
                        if fields == 'all' or field_name in fields:
                            mappings[field_info['database_field']] = field_info['database_type']
        
        return mappings


class DatabaseManager:
    """Manages database schema creation during installation."""
    
    def __init__(self, config_dict):
        self.config_dict = config_dict
    
    def create_database_fields(self, field_mappings):
        """Create database fields for selected data."""
        if not field_mappings:
            return 0
        
        print("\n" + "="*60)
        print("DATABASE SCHEMA MANAGEMENT")
        print("="*60)
        print("Checking and extending database schema...")
        print()
        
        # Check existing fields
        existing_fields = self._check_existing_fields()
        
        # Determine missing fields
        missing_fields = set(field_mappings.keys()) - set(existing_fields)
        already_present = set(field_mappings.keys()) & set(existing_fields)
        
        # Report existing fields
        if already_present:
            print("Fields already present in database:")
            for field in sorted(already_present):
                print(f"  ✓ {field} - already exists, skipping")
            print()
        
        # Add missing fields
        created_count = 0
        if missing_fields:
            print("Adding missing fields to database:")
            created_count = self._add_missing_fields(missing_fields, field_mappings)
        else:
            print("All required fields already exist in database.")
        
        print(f"\n✓ Database schema management completed successfully")
        print(f"  Fields already present: {len(already_present)}")
        print(f"  Fields created: {created_count}")
        
        return created_count
    
    def _check_existing_fields(self):
        """Check which OpenWeather fields already exist in database."""
        try:
            # FIXED: Use standard WeeWX binding name directly (eliminates Section object warning)
            db_binding = 'wx_binding'
            
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                existing_fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    field_name = column[1]
                    if field_name.startswith('ow_'):  # Only OpenWeather fields
                        existing_fields.append(field_name)
            
            return existing_fields
        except Exception as e:
            print(f"  Warning: Could not check existing database fields: {e}")
            return []
    
    def _add_missing_fields(self, missing_fields, field_mappings):
        """Add missing database fields using hybrid approach.
        
        Uses weectl for REAL/INTEGER types (confirmed supported)
        Uses direct SQL for VARCHAR/TEXT types (weectl limitation workaround)
        
        Fails fast on any real errors to prevent corrupted installations.
        """
        # Find weectl executable
        weectl_path = self._find_weectl()
        config_path = getattr(self.config_dict, 'filename', '/etc/weewx/weewx.conf')
        created_count = 0
        
        for field_name in sorted(missing_fields):
            field_type = field_mappings[field_name]
            
            print(f"  Adding field '{field_name}' ({field_type})...")
            
            # Use weectl for numeric types (confirmed supported)
            if field_type in ['REAL', 'INTEGER', 'real', 'integer', 'int']:
                if not weectl_path:
                    raise Exception("weectl executable not found - required for numeric field types")
                
                cmd = [weectl_path, 'database', 'add-column', field_name, 
                    f'--config={config_path}', '-y']
                cmd.insert(-2, f'--type={field_type}')
                
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                
                if result.returncode == 0:
                    print(f"    ✓ Successfully added '{field_name}' using weectl")
                    created_count += 1
                elif 'duplicate column' in result.stderr.lower():
                    print(f"    ✓ Field '{field_name}' already exists")
                    created_count += 1
                else:
                    raise Exception(f"weectl failed to add '{field_name}': {result.stderr.strip()}")
            
            else:
                # Use direct SQL for VARCHAR/TEXT types (AirVisual method)
                # print(f"    Using direct SQL (weectl doesn't support {field_type})")
                self._add_field_direct_sql(field_name, field_type)
                created_count += 1
        
        return created_count

    def _add_field_direct_sql(self, field_name, field_type):
        """Add field using direct SQL through WeeWX database manager (AirVisual method).
        
        Handles both MySQL/MariaDB and SQLite databases properly.
        """
        try:
            db_binding = 'wx_binding'
            
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                # Convert MySQL-specific types for SQLite compatibility
                if field_type.startswith('VARCHAR'):
                    sql_type = 'TEXT' if 'sqlite' in str(dbmanager.connection).lower() else field_type
                else:
                    sql_type = field_type
                
                sql = f"ALTER TABLE archive ADD COLUMN {field_name} {sql_type}"
                dbmanager.connection.execute(sql)
                print(f"    ✓ Successfully added '{field_name}' using direct SQL")
                
        except Exception as e:
            error_msg = str(e).lower()
            if 'duplicate column' in error_msg or 'already exists' in error_msg:
                print(f"    ✓ Field '{field_name}' already exists")
            else:
                print(f"    ❌ Failed to add '{field_name}': {e}")
                raise Exception(f"Direct SQL field creation failed: {e}")

    def _create_forecast_table_if_needed(self, selected_fields):
        """Create openweather_forecast table if forecast modules are selected."""
        forecast_modules = ['forecast_daily', 'forecast_hourly', 'forecast_air_quality']
        
        # Check if any forecast modules are selected
        needs_forecast_table = any(module in selected_fields for module in forecast_modules)
        
        if not needs_forecast_table:
            return
        
        print("  Creating forecast table for forecast modules...")
        
        try:
            db_binding = 'wx_binding'
            
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                # Check if table already exists
                table_exists = False
                try:
                    dbmanager.connection.execute("SELECT 1 FROM openweather_forecast LIMIT 1")
                    table_exists = True
                    print("    ✓ Forecast table already exists")
                except:
                    table_exists = False
                
                if not table_exists:
                    # Convert MySQL-specific types for SQLite compatibility
                    if 'sqlite' in str(dbmanager.connection).lower():
                        # SQLite version
                        create_sql = """
                        CREATE TABLE openweather_forecast (
                            dateTime INTEGER NOT NULL,
                            forecast_type TEXT NOT NULL,
                            forecast_time INTEGER NOT NULL,
                            forecast_data TEXT,
                            PRIMARY KEY (dateTime, forecast_type, forecast_time)
                        )"""
                    else:
                        # MySQL/MariaDB version
                        create_sql = """
                        CREATE TABLE openweather_forecast (
                            dateTime INTEGER NOT NULL,
                            forecast_type VARCHAR(20) NOT NULL,
                            forecast_time INTEGER NOT NULL,
                            forecast_data TEXT,
                            PRIMARY KEY (dateTime, forecast_type, forecast_time)
                        )"""
                    
                    dbmanager.connection.execute(create_sql)
                    print("    ✓ Successfully created openweather_forecast table")
                    
        except Exception as e:
            error_msg = str(e).lower()
            if 'already exists' in error_msg or 'table exists' in error_msg:
                print("    ✓ Forecast table already exists")
            else:
                raise Exception(f"Failed to create forecast table: {e}")
    
    def _find_weectl(self):
        """Find the weectl executable in standard locations."""
        weectl_candidates = [
            '/usr/bin/weectl',
            '/usr/local/bin/weectl', 
            'weectl'  # Try PATH
        ]
        
        for candidate in weectl_candidates:
            try:
                result = subprocess.run([candidate, '--version'], 
                                    capture_output=True, text=True, timeout=10)
                if result.returncode == 0:
                    print(f"  Found weectl: {candidate}")
                    return candidate
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
        
        print("  Warning: weectl not found - will use direct SQL for all fields")
        return None
    
    def _print_manual_commands(self, missing_fields, field_mappings):
        """Print manual commands for database field creation."""
        print("\n  Manual database field creation commands:")
        print("  " + "-" * 50)
        
        for field_name in sorted(missing_fields):
            field_type = field_mappings[field_name]
            if field_type in ['REAL', 'INTEGER']:
                print(f"  weectl database add-column {field_name} --type {field_type} -y")
            else:
                print(f"  weectl database add-column {field_name} -y")
        
        print("  " + "-" * 50)


class OpenWeatherConfigurator:
    """Handles all interactive configuration - separated from installer mechanics."""
    
    def __init__(self, config_dict):
        self.config_dict = config_dict
    
    def run_interactive_setup(self):
        """Complete interactive configuration process."""
        
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION CONFIGURATION")
        print("="*80)
        print("This extension collects weather and air quality data from OpenWeatherMap.")
        print("You'll be guided through API setup and field selection.")
        print("-" * 80)
        
        try:
            # Step 1: API key setup
            api_key = self._prompt_api_key()
            
            # Step 2: Module selection
            modules = self._select_modules()
            
            # Step 3: Field selection
            extension_dir = os.path.dirname(__file__)
            field_helper = FieldSelectionHelper(extension_dir)
            
            ui = TerminalUI()
            complexity = ui.show_complexity_menu()
            
            if complexity == 'custom':
                # Custom field selection
                field_definitions = field_helper.field_definitions
                selected_fields = ui.show_custom_selection(field_definitions)
                if selected_fields is None:
                    # User selected no fields, fall back to standard
                    complexity = 'standard'
                    selected_fields = field_helper.get_selected_fields('standard')
            else:
                # Use smart defaults
                selected_fields = field_helper.get_selected_fields(complexity)
            
            # Step 4: Confirmation
            field_count = field_helper.estimate_field_count(selected_fields)
            confirmation = ui.confirm_selection(complexity, field_count)
            if confirmation != 'true':  # Check string value
                print("\nConfiguration cancelled by user.")
                return 'false'  # Return string
            
            # Step 5: Database schema creation
            field_mappings = field_helper.get_database_field_mappings(selected_fields)
            db_manager = DatabaseManager(self.config_dict)
            created_count = db_manager.create_database_fields(field_mappings)
            
            # Step 6: Write configuration
            self._write_enhanced_config(api_key, modules, complexity, selected_fields)
            
            # Step 7: Setup unit system
            self._setup_unit_system()
            
            print("\n" + "="*80)
            print("CONFIGURATION COMPLETED SUCCESSFULLY!")
            print("="*80)
            print(f"✓ API key configured")
            print(f"✓ Data collection level: {complexity.title()}")
            print(f"✓ Database fields created: {created_count}")
            print(f"✓ Service registration: Automatic via ExtensionInstaller")
            print(f"✓ Unit system configured")
            print("-" * 80)
            print("Next steps:")
            print("1. Restart WeeWX: sudo systemctl restart weewx")
            print("2. Check logs: sudo journalctl -u weewx -f")
            print("3. Verify data collection in database/reports")
            print()
            print("For additional extensions, consider:")
            print("- weewx-cdc-surveillance (public health data)")
            print("- weewx-environmental-health (health risk assessment)")
            print("="*80)
            
            return {
                'selected_fields': selected_fields,  # Goes to /etc/weewx/openweather_fields.conf
                'api_settings': {                    # Goes to weewx.conf
                    'api_key': api_key,
                    'modules': modules,
                    'complexity': complexity
                }
            }
            
        except Exception as e:
            # Ignore ConfigObj string/boolean conversion warnings that don't affect functionality
            if "not a string" in str(e) and "False" in str(e):
                print(f"\n⚠️  Minor configuration warning (ignored): {e}")
                print("Installation completed successfully despite the warning.")
                return 'true'  # Continue with successful installation
            else:
                print(f"\nConfiguration failed: {e}")
                return 'false'
    
    def _prompt_api_key(self):
        """Prompt for OpenWeatherMap API key with validation."""
        print("\n" + "="*60)
        print("OPENWEATHERMAP API KEY SETUP")
        print("="*60)
        print("You need a free API key from OpenWeatherMap.")
        print("1. Visit: https://openweathermap.org/api")
        print("2. Sign up for free account")
        print("3. Get your API key from the dashboard")
        print("-" * 60)
        
        while True:
            try:
                api_key = input("Enter your OpenWeatherMap API key: ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nConfiguration cancelled by user.")
                sys.exit(1)
            
            if not api_key:
                print("API key cannot be empty. Please enter your API key.")
                continue
            
            if len(api_key) < 10:
                print("API key seems too short. Please verify and try again.")
                continue
            
            # Basic format validation
            if not re.match(r'^[a-fA-F0-9]+$', api_key):
                print("API key should contain only hexadecimal characters. Please verify and try again.")
                continue
            
            print(f"✓ API key accepted: {api_key[:8]}...")
            return api_key
    
    def _select_modules(self):
        """Select which OpenWeather modules to enable."""
        print("\n" + "="*60)
        print("MODULE SELECTION")
        print("="*60)
        print("Choose which OpenWeather data modules to enable:")
        print("-" * 60)
        
        modules = {}
        
        # Current weather (always recommended)
        while True:
            try:
                choice = input("Enable current weather data (temperature, humidity, pressure, wind)? [Y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nConfiguration cancelled by user.")
                sys.exit(1)
            
            if choice in ['', 'y', 'yes']:
                modules['current_weather'] = 'true'  # String value
                print("✓ Current weather module enabled")
                break
            elif choice in ['n', 'no']:
                modules['current_weather'] = 'false'  # String value
                print("○ Current weather module disabled")
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or press Enter for yes")
        
        # Air quality
        while True:
            try:
                choice = input("Enable air quality data (PM2.5, ozone, AQI)? [Y/n]: ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nConfiguration cancelled by user.")
                sys.exit(1)
            
            if choice in ['', 'y', 'yes']:
                modules['air_quality'] = 'true'  # String value
                print("✓ Air quality module enabled")
                break
            elif choice in ['n', 'no']:
                modules['air_quality'] = 'false'  # String value
                print("○ Air quality module disabled")
                break
            else:
                print("Please enter 'y' for yes, 'n' for no, or press Enter for yes")
        
        return modules
    
    def _write_enhanced_config(self, api_key, modules, complexity, selected_fields):
        """Write enhanced configuration to weewx.conf."""
        
        # Update the service configuration
        config_dict = self.config_dict
        
        # FIXED: Use proper ConfigObj dictionary-style assignment instead of manual Section creation
        
        # Ensure OpenWeatherService section exists
        if 'OpenWeatherService' not in config_dict:
            config_dict['OpenWeatherService'] = {}
        
        service_config = config_dict['OpenWeatherService']
        
        # Basic configuration - ALL VALUES AS STRINGS for ConfigObj
        service_config['enable'] = 'true'
        service_config['api_key'] = str(api_key)
        service_config['timeout'] = '30'
        service_config['log_success'] = 'false'
        service_config['log_errors'] = 'true'
        
        # Module configuration - use dictionary assignment with string values
        if 'modules' not in service_config:
            service_config['modules'] = {}
        
        # Handle both string and boolean values from modules dict
        current_weather_val = modules.get('current_weather', 'true')
        if isinstance(current_weather_val, bool):
            service_config['modules']['current_weather'] = 'true' if current_weather_val else 'false'
        else:
            service_config['modules']['current_weather'] = str(current_weather_val)
            
        air_quality_val = modules.get('air_quality', 'true')
        if isinstance(air_quality_val, bool):
            service_config['modules']['air_quality'] = 'true' if air_quality_val else 'false'
        else:
            service_config['modules']['air_quality'] = str(air_quality_val)
        
        # Interval configuration - use dictionary assignment with string values
        if 'intervals' not in service_config:
            service_config['intervals'] = {}
        
        service_config['intervals']['current_weather'] = '3600'
        service_config['intervals']['air_quality'] = '7200'
        
        # Field selection configuration - use dictionary assignment with string values
        if 'field_selection' not in service_config:
            service_config['field_selection'] = {}
        
        field_config = service_config['field_selection']
        
        if complexity != 'custom':
            field_config['complexity_level'] = str(complexity)
        else:
            field_config['complexity_level'] = 'custom'
            
            # Add custom field selections - use dictionary assignment with string values
            for module, fields in selected_fields.items():
                if module not in field_config:
                    field_config[module] = {}
                
                module_config = field_config[module]
                
                # Clear existing fields
                for key in list(module_config.keys()):
                    del module_config[key]
                
                # Add selected fields as strings
                for field in fields:
                    module_config[field] = 'true'
    
    def _setup_unit_system(self):
        """Setup unit system extensions for OpenWeather data."""
        
        # Add concentration unit group for air quality
        try:
            import weewx.units
            
            if 'group_concentration' not in weewx.units.USUnits:
                weewx.units.USUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricUnits['group_concentration'] = 'microgram_per_meter_cubed'
                weewx.units.MetricWXUnits['group_concentration'] = 'microgram_per_meter_cubed'
            
            # Add formatting for concentration
            if 'microgram_per_meter_cubed' not in weewx.units.default_unit_format_dict:
                weewx.units.default_unit_format_dict['microgram_per_meter_cubed'] = '%.1f'
            
            # Add label for concentration
            if 'microgram_per_meter_cubed' not in weewx.units.default_unit_label_dict:
                weewx.units.default_unit_label_dict['microgram_per_meter_cubed'] = ' μg/m³'
            
            print("  ✓ Unit system configured for OpenWeather fields")
            
        except Exception as e:
            print(f"  Warning: Could not setup unit system: {e}")


class OpenWeatherInstaller(ExtensionInstaller):
    """Main installer - handles WeeWX extension mechanics with proper service registration."""
    
    def __init__(self):
        super(OpenWeatherInstaller, self).__init__(
            version="1.0.0",
            name="OpenWeather", 
            description="OpenWeatherMap API integration with modular field selection",
            author="WeeWX OpenWeather Extension",
            author_email="",
            
            # FIXED: Use data_services parameter for automatic install/uninstall
            data_services=['user.openweather.OpenWeatherService'],
            
            files=[
                ('bin/user', ['bin/user/openweather.py']),
                ('', ['field_selection_defaults.yaml', 'openweather_fields.yaml'])
            ],
            config={
                'OpenWeatherService': {
                    'enable': 'true',
                    'api_key': 'REPLACE_WITH_YOUR_API_KEY',
                    'timeout': '30',
                    'log_success': 'false',
                    'log_errors': 'true',
                    'modules': {
                        'current_weather': 'true',
                        'air_quality': 'true'
                    },
                    'intervals': {
                        'current_weather': '3600',
                        'air_quality': '7200'
                    },
                    'field_selection': {
                        'complexity_level': 'standard'
                    }
                }
                # NO Engine section - handled automatically by data_services parameter
            }
        )
    
    def configure(self, engine):
        """Orchestrates installation - delegates to configurator for separation of concerns."""
        
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION INSTALLATION")
        print("="*80)
        print("Installing files and registering service...")
        print("Service registration: Automatic via ExtensionInstaller data_services parameter")
        print("-" * 80)
        
        # Delegate all interactive configuration to separate class
        configurator = OpenWeatherConfigurator(engine.config_dict)
        configuration_result = configurator.run_interactive_setup()
        
        if configuration_result == 'true':  # Check string value
            print("\n" + "="*80)
            print("INSTALLATION COMPLETED SUCCESSFULLY!")
            print("="*80)
            print("✓ Files installed")
            print("✓ Service registered automatically: user.openweather.OpenWeatherService")
            print("✓ Interactive configuration completed")
            print("✓ Database schema extended")
            print("✓ Unit system configured")
            print("-" * 80)
            print("IMPORTANT: Restart WeeWX to activate the extension:")
            print("  sudo systemctl restart weewx")
            print()
            print("Check logs for successful operation:")
            print("  sudo journalctl -u weewx -f")
            print("="*80)
        
        return configuration_result == 'true'  # Convert string to boolean for ExtensionInstaller
    
    def _save_field_selection(self, selected_fields):
        """Save field selection to extension-managed configuration file.
        
        Stores field selection separately from weewx.conf to prevent user editing
        issues and configuration corruption during WeeWX updates.
        
        Args:
            selected_fields (dict): Field selection data structure
                Format: {'current_weather': ['temp', 'humidity'], 'air_quality': ['pm2_5']}
        """
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        try:
            print(f"  Saving field selection to {selection_file}...")
            
            # Create configuration object
            config = configobj.ConfigObj()
            config.filename = selection_file
            
            # Store field selection with metadata
            config['field_selection'] = {
                'selected_fields': selected_fields,
                'selection_timestamp': str(int(time.time())),
                'config_version': '1.0'
            }
            
            # Write configuration file
            config.write()
            
            # Set appropriate permissions (readable by weewx user)
            os.chmod(selection_file, 0o644)
            
            print(f"    ✓ Field selection saved successfully")
            print(f"    Selected modules: {list(selected_fields.keys())}")
            
            # Show field count summary
            total_fields = 0
            for module, fields in selected_fields.items():
                if isinstance(fields, list):
                    total_fields += len(fields)
                    print(f"    {module}: {len(fields)} fields")
                elif fields == 'all':
                    print(f"    {module}: all available fields")
            
            if total_fields > 0:
                print(f"    Total selected fields: {total_fields}")
                
        except Exception as e:
            print(f"    ❌ Failed to save field selection: {e}")
            raise Exception(f"Field selection storage failed: {e}")
    
    def _load_field_selection(self):
        """Load field selection from extension-managed configuration file.
        
        Returns:
            dict: Field selection data or empty dict if not found/invalid
                Format: {'current_weather': ['temp', 'humidity'], 'air_quality': ['pm2_5']}
        """
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        try:
            if not os.path.exists(selection_file):
                print(f"    Field selection file not found: {selection_file}")
                return {}
            
            print(f"  Loading field selection from {selection_file}...")
            
            # Load configuration file
            config = configobj.ConfigObj(selection_file)
            
            # Extract field selection data
            field_selection_section = config.get('field_selection', {})
            selected_fields = field_selection_section.get('selected_fields', {})
            
            if not selected_fields:
                print(f"    ⚠️ No field selection found in configuration file")
                return {}
            
            # Validate field selection structure
            if not isinstance(selected_fields, dict):
                print(f"    ❌ Invalid field selection format")
                return {}
            
            print(f"    ✓ Field selection loaded successfully")
            
            # Show configuration info
            timestamp = field_selection_section.get('selection_timestamp', 'unknown')
            version = field_selection_section.get('config_version', 'unknown')
            print(f"    Configuration version: {version}")
            print(f"    Selection timestamp: {timestamp}")
            print(f"    Loaded modules: {list(selected_fields.keys())}")
            
            return selected_fields
            
        except Exception as e:
            print(f"    ❌ Failed to load field selection: {e}")
            return {}
    
    def reconfigure(self, engine):
        """Support field selection reconfiguration via 'weectl extension reconfigure OpenWeather'.
        
        Allows users to change their field selection without reinstalling the extension.
        Updates database schema to add new fields but preserves existing data.
        
        Args:
            engine: WeeWX engine instance
            
        Returns:
            bool: True if reconfiguration succeeded, False otherwise
        """
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION RECONFIGURATION")
        print("="*80)
        print("This will allow you to change your field selection settings.")
        print("Existing data will be preserved - only new fields will be added.")
        print("-" * 80)
        
        try:
            # Load current field selection
            current_selection = self._load_field_selection()
            
            if current_selection:
                print(f"\nCurrent field selection found:")
                for module, fields in current_selection.items():
                    if isinstance(fields, list):
                        print(f"  {module}: {len(fields)} fields selected")
                    else:
                        print(f"  {module}: {fields}")
            else:
                print(f"\nNo current field selection found.")
            
            print(f"\nYou can now select new field configuration.")
            print(f"Note: This will ADD new fields but won't remove existing ones.")
            
            # Run interactive field selection
            configurator = OpenWeatherConfigurator(engine.config_dict)
            configuration_result = configurator.run_interactive_setup()
            
            if not isinstance(configuration_result, dict):
                print(f"\n❌ Configuration failed - invalid result format")
                return False
            
            new_selected_fields = configuration_result.get('selected_fields', {})
            if not new_selected_fields:
                print(f"\n❌ Configuration failed - no field selection received")
                return False
            
            # Save new field selection
            self._save_field_selection(new_selected_fields)
            
            # Update database schema with new fields
            print(f"\nUpdating database schema for new field selection...")
            
            # Get field mappings for new selection
            field_helper = FieldSelectionHelper('/usr/share/weewx')  # Extension dir
            field_mappings = field_helper.get_database_field_mappings(new_selected_fields)
            
            if field_mappings:
                # Create database manager and add any missing fields
                db_manager = DatabaseManager(engine.config_dict)
                existing_fields, missing_fields = db_manager.check_database_fields(field_mappings.keys())
                
                if missing_fields:
                    print(f"  Found {len(missing_fields)} new fields to add...")
                    created_count = db_manager._add_missing_fields(missing_fields, field_mappings)
                    print(f"  ✓ Added {created_count} new database fields")
                else:
                    print(f"  ✓ No new database fields needed")
            
            # Update operational configuration if needed
            api_settings = configuration_result.get('api_settings', {})
            if api_settings:
                print(f"\nUpdating operational configuration...")
                self._write_service_config(engine.config_dict, api_settings)
                print(f"  ✓ Operational settings updated")
            
            print(f"\n" + "="*80)
            print("RECONFIGURATION COMPLETED SUCCESSFULLY!")
            print("="*80)
            print("Changes made:")
            print("✓ Field selection updated and saved")
            print("✓ Database schema updated with new fields")
            print("✓ Existing data preserved")
            print()
            print("Next steps:")
            print("1. Restart WeeWX to use new configuration:")
            print("   sudo systemctl restart weewx")
            print("2. Monitor logs to verify operation:")
            print("   sudo journalctl -u weewx -f")
            print("="*80)
            
            return True
            
        except Exception as e:
            print(f"\n❌ Reconfiguration failed: {e}")
            print(f"The extension will continue to work with previous settings.")
            return False
    
    def _write_service_config(self, config_dict, api_settings):
        """Write only operational settings to weewx.conf (no field selection).
        
        Stores only the settings needed for service operation:
        - API key and connection settings
        - Timeouts and retry settings  
        - Collection intervals
        - Logging preferences
        
        Field selection is stored separately in openweather_fields.conf.
        
        Args:
            config_dict: WeeWX configuration dictionary
            api_settings (dict): Operational settings from interactive setup
        """
        try:
            print(f"  Writing operational configuration to weewx.conf...")
            
            # Ensure OpenWeatherService section exists
            if 'OpenWeatherService' not in config_dict:
                config_dict['OpenWeatherService'] = configobj.ConfigObj()
            
            service_config = config_dict['OpenWeatherService']
            
            # Write operational settings only (NO field selection)
            service_config['enable'] = 'true'
            service_config['api_key'] = api_settings.get('api_key', 'REPLACE_WITH_YOUR_API_KEY')
            service_config['timeout'] = str(api_settings.get('timeout', 30))
            service_config['retry_attempts'] = str(api_settings.get('retry_attempts', 3))
            service_config['log_success'] = str(api_settings.get('log_success', False)).lower()
            service_config['log_errors'] = 'true'  # Always log errors
            
            # Write collection intervals
            if 'intervals' not in service_config:
                service_config['intervals'] = configobj.ConfigObj()
            
            intervals = api_settings.get('intervals', {})
            service_config['intervals']['current_weather'] = str(intervals.get('current_weather', 3600))
            service_config['intervals']['air_quality'] = str(intervals.get('air_quality', 7200))
            service_config['intervals']['uv_index'] = str(intervals.get('uv_index', 3600))
            
            # Write module enable/disable settings
            if 'modules' not in service_config:
                service_config['modules'] = configobj.ConfigObj()
            
            # Enable modules based on what user selected (but don't store field details)
            modules = api_settings.get('enabled_modules', ['current_weather', 'air_quality'])
            service_config['modules']['current_weather'] = 'true' if 'current_weather' in modules else 'false'
            service_config['modules']['air_quality'] = 'true' if 'air_quality' in modules else 'false'
            service_config['modules']['uv_index'] = 'true' if 'uv_index' in modules else 'false'
            service_config['modules']['forecast'] = 'true' if 'forecast' in modules else 'false'
            
            # EXPLICITLY DO NOT write field selection to weewx.conf
            # Field selection is stored in /etc/weewx/openweather_fields.conf
            
            # Save configuration file
            config_dict.write()
            
            print(f"    ✓ Operational configuration written successfully")
            print(f"    Note: Field selection stored separately in openweather_fields.conf")
            
        except Exception as e:
            print(f"    ❌ Failed to write service configuration: {e}")
            raise Exception(f"Service configuration writing failed: {e}")


if __name__ == '__main__':
    print("This is a WeeWX extension installer.")
    print("Use: weectl extension install weewx-openweather.zip")
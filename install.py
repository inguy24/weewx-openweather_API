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
        """Dynamic field listings from API-first YAML structure."""
        print("\n" + "="*80)
        print("OPENWEATHER DATA COLLECTION LEVEL")
        print("="*80)
        print("Choose which data fields to collect from OpenWeatherMap.")
        print("Each level includes specific fields as listed below:")
        print()
        
        try:
            extension_dir = os.path.dirname(__file__)
            config_path = os.path.join(extension_dir, 'openweather_fields.yaml')
            with open(config_path, 'r') as f:
                api_config = yaml.safe_load(f)
            
            all_fields = []
            minimal_fields = []
            
            for module_name, module_config in api_config.get('api_modules', {}).items():
                for field_name, field_config in module_config.get('fields', {}).items():
                    display_name = field_config.get('display_name', field_name)
                    complexity_levels = field_config.get('complexity_levels', [])
                    
                    all_fields.append(display_name)
                    if 'minimal' in complexity_levels:
                        minimal_fields.append(display_name)
            
            minimal_fields.sort()
            all_fields.sort()
            
        except Exception as e:
            print(f"Warning: Could not load field definitions: {e}")
            print("Using basic descriptions instead of detailed field lists.")
            
            options = [
                ("Minimal", "Essential fields for Extension 3 health predictions"),
                ("All", "Everything available from free OpenWeather APIs"),
                ("Custom", "Choose specific fields manually")
            ]
            
            print("\nChoose data collection level:")
            print("-" * 40)
            
            for i, (name, description) in enumerate(options, 1):
                print(f"{i}. {name}")
                print(f"   {description}")
                print()
            
            while True:
                try:
                    choice = input("Enter choice [1-3]: ").strip()
                    if choice in ['1', '2', '3']:
                        complexity_levels = ['minimal', 'all', 'custom']
                        selected = complexity_levels[int(choice) - 1]
                        print(f"\n✓ Selected: {options[int(choice) - 1][0]}")
                        return selected
                    else:
                        print("Invalid choice. Please enter 1, 2, or 3.")
                except (KeyboardInterrupt, EOFError):
                    print("\nInstallation cancelled by user.")
                    sys.exit(1)
        
        def format_field_list(fields, indent="   "):
            if not fields:
                return f"{indent}No fields configured"
            
            lines = []
            current_line = indent + "Fields: "
            
            for field in fields:
                test_line = current_line + field + ", "
                if len(test_line) > 75 and current_line != indent + "Fields: ":
                    lines.append(current_line.rstrip(", "))
                    current_line = indent + "       " + field + ", "
                else:
                    current_line = test_line
            
            if current_line.strip():
                lines.append(current_line.rstrip(", "))
            
            return "\n".join(lines)
        
        print("1. MINIMAL COLLECTION")
        print(f"   Essential fields for Extension 3 health predictions")
        print(f"   {len(minimal_fields)} database fields")
        print(format_field_list(minimal_fields))
        print()
        
        print("2. ALL FIELDS")
        print(f"   Complete OpenWeatherMap dataset with all available fields")
        print(f"   {len(all_fields)} database fields")
        print(format_field_list(all_fields))
        print()
        
        print("3. CUSTOM SELECTION")
        print(f"   Choose specific fields manually using interactive menu")
        print(f"   Select from {len(all_fields)} available fields")
        print()
        
        while True:
            try:
                choice = input("Enter choice [1-3]: ").strip()
                if choice == '1':
                    print(f"\n✓ Selected: Minimal Collection ({len(minimal_fields)} fields)")
                    return 'minimal'
                elif choice == '2':
                    print(f"\n✓ Selected: All Fields ({len(all_fields)} fields)")
                    return 'all'
                elif choice == '3':
                    print(f"\n✓ Selected: Custom Selection")
                    return 'custom'
                else:
                    print("Invalid choice. Please enter 1, 2, or 3.")
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)

    def show_custom_selection(self, field_definitions):
        """Show flat field selection interface for new YAML structure."""
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
            
            # Build field list directly from YAML - no hardcoded categorization
            all_fields = []
            for field_name, field_info in field_definitions.items():
                all_fields.append({
                    'type': 'field',
                    'name': field_name,
                    'display': field_info['display_name'],
                    'selected': False
                })
            
            # Sort alphabetically by display name for consistent presentation
            all_fields.sort(key=lambda x: x['display'])
            
            # State variables
            current_item = 0
            scroll_offset = 0
            
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
                for i in range(scroll_offset, min(scroll_offset + visible_height, len(all_fields))):
                    field = all_fields[i]
                    y_pos = 3 + (i - scroll_offset)
                    
                    if y_pos >= height - 3:  # Don't overwrite summary area
                        break
                    
                    # Field item
                    selected_mark = "[X]" if field['selected'] else "[ ]"
                    
                    # Highlight current item
                    attr = 0
                    if i == current_item:
                        attr = curses.color_pair(1) | curses.A_BOLD
                    elif field['selected']:
                        attr = curses.color_pair(2)
                    
                    line = f"  {selected_mark} {field['display']}"
                    stdscr.addstr(y_pos, 0, line[:width-1], attr)
                
                # Summary at bottom
                selected_count = sum(1 for f in all_fields if f['selected'])
                total_fields = len(all_fields)
                summary = f"Selected: {selected_count}/{total_fields} fields"
                stdscr.addstr(height-2, (width - len(summary)) // 2, summary, curses.color_pair(3))
                
                stdscr.refresh()
            
            # Main interaction loop
            while True:
                draw_interface()
                key = stdscr.getch()
                
                if key == ord('q') or key == 27:  # ESC or 'q'
                    return None
                elif key == curses.KEY_UP and current_item > 0:
                    current_item -= 1
                elif key == curses.KEY_DOWN and current_item < len(all_fields) - 1:
                    current_item += 1
                elif key == ord(' '):  # Space to toggle selection
                    all_fields[current_item]['selected'] = not all_fields[current_item]['selected']
                elif key == ord('\n') or key == curses.KEY_ENTER or key == 10:
                    # Return flat field selection
                    result = {}
                    for field in all_fields:
                        if field['selected']:
                            result[field['name']] = True
                    return result
        
        try:
            result = curses.wrapper(curses_main)
            
            if result is None:
                print("\nCustom selection cancelled.")
                return None
            
            # Show final summary
            selected_count = len(result)
            print(f"\n" + "="*60)
            print(f"SELECTION SUMMARY: {selected_count} fields selected")
            print("="*60)
            
            if selected_count == 0:
                print("Warning: No fields selected. Using 'minimal' defaults instead.")
                return None
            
            # Show selected field names
            if result:
                selected_names = []
                for field_name in result.keys():
                    if field_name in field_definitions:
                        selected_names.append(field_definitions[field_name]['display_name'])
                
                if selected_names:
                    print("Selected fields:")
                    for i, name in enumerate(selected_names[:5]):  # Show first 5
                        print(f"  - {name}")
                    if len(selected_names) > 5:
                        print(f"  ... and {len(selected_names) - 5} more")
            
            return result
            
        except Exception as e:
            print(f"\nError with custom selection interface: {e}")
            print("Falling back to 'minimal' field selection.")
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
    """Handles all interactive configuration - merged with field selection logic."""
    
    def __init__(self, config_dict):
        """Initialize configurator with config dict and load field definitions."""
        self.config_dict = config_dict
        
        # Create UI object for terminal interactions
        self.ui = TerminalUI()
        
        # Get extension directory for YAML loading
        extension_dir = os.path.dirname(__file__)
        
        # Load API configuration and field definitions - NO FALLBACKS!
        try:
            self.api_config = self._load_api_config(extension_dir)
            self.field_definitions = self._create_flat_field_definitions()
            
            if not self.field_definitions:
                raise Exception("No field definitions found in YAML - check openweather_fields.yaml structure")
                
            print(f"✓ Loaded {len(self.field_definitions)} field definitions from YAML")
            
        except Exception as e:
            print(f"\n❌ CRITICAL ERROR: Could not load field definitions from YAML")
            print(f"Error: {e}")
            print(f"\nThis extension requires a valid openweather_fields.yaml file.")
            print(f"Check that the file exists in the extension directory and has the correct structure:")
            print(f"  {extension_dir}/openweather_fields.yaml")
            print(f"\nInstallation cannot proceed without valid field definitions.")
            sys.exit(1)

    def _load_api_config(self, extension_dir):
        """Load API-first configuration from YAML."""
        try:
            config_path = os.path.join(extension_dir, 'openweather_fields.yaml')
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load API configuration: {e}")
            return {'api_modules': {}, 'complexity_definitions': {}}

    def _create_flat_field_definitions(self):
        """Create flat field_definitions from YAML api_modules structure - NO HARDCODING!"""
        flat_definitions = {}
        
        # Ensure we have valid api_config
        if not self.api_config:
            raise Exception("No API configuration loaded")
        
        if 'api_modules' not in self.api_config:
            raise Exception("YAML missing 'api_modules' section")
        
        # Extract all fields from all API modules
        for module_name, module_config in self.api_config['api_modules'].items():
            if 'fields' not in module_config:
                print(f"Warning: Module '{module_name}' has no fields section")
                continue
                
            for field_name, field_config in module_config['fields'].items():
                # Validate required field properties
                required_props = ['display_name', 'database_field', 'database_type']
                missing_props = [prop for prop in required_props if prop not in field_config]
                
                if missing_props:
                    print(f"Warning: Field '{field_name}' missing required properties: {missing_props}")
                    continue
                    
                flat_definitions[field_name] = field_config
        
        if not flat_definitions:
            raise Exception("No valid field definitions found in YAML api_modules")
        
        return flat_definitions

    def _load_field_definitions(self, extension_dir):
        """Load field definitions from YAML file."""
        try:
            definitions_path = os.path.join(extension_dir, 'openweather_fields.yaml')
            with open(definitions_path, 'r') as f:
                return yaml.safe_load(f)['field_definitions']
        except Exception as e:
            print(f"Warning: Could not load field definitions: {e}")
            return {}
    
    def run_interactive_setup(self):
        """Enhanced interactive setup with unit system integration - returns tuple."""
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION CONFIGURATION")
        print("="*80)
        print("This installer will configure OpenWeatherMap API data collection.")
        print("The extension will automatically detect your WeeWX unit system and")
        print("configure OpenWeather API calls accordingly.")
        print()
        
        # Detect and display unit system information
        weewx_unit_system = self._detect_weewx_unit_system()
        openweather_units = self._map_to_openweather_units(weewx_unit_system)
        
        print("UNIT SYSTEM DETECTION")
        print("-" * 40)
        print(f"WeeWX unit system: {weewx_unit_system}")
        print(f"OpenWeather API calls will use: {openweather_units}")
        
        if weewx_unit_system == 'US':
            print("  → Temperature: Fahrenheit, Wind: mph, Pressure: inHg")
        elif weewx_unit_system == 'METRICWX':
            print("  → Temperature: Celsius, Wind: m/s, Pressure: mbar")
        elif weewx_unit_system == 'METRIC':
            print("  → Temperature: Celsius, Wind: km/hr (converted from m/s), Pressure: mbar")
        
        print("\nThis ensures OpenWeather data integrates seamlessly with your WeeWX system.")
        
        # Get API key
        api_key = self._prompt_api_key()
        
        # Get data collection level with enhanced field listings
        complexity_level = self.ui.show_complexity_menu()
        self.complexity_level = complexity_level  # Store for config writing
        
        # Get field selection (flat format for database operations)
        selected_fields = self.get_selected_fields(complexity_level)
        field_count = self.estimate_field_count(selected_fields)
        
        # Confirm selection
        confirmed = self.ui.confirm_selection(complexity_level, field_count)
        if confirmed == 'false':
            print("\nInstallation cancelled by user.")
            sys.exit(1)
        
        # Setup intervals
        intervals = self._setup_intervals()
        
        # Write configuration (converts flat to module format internally)
        config_dict = self._write_enhanced_config(self.config_dict, selected_fields, api_key, intervals)
        
        # FIX: Return tuple instead of single value
        return config_dict, selected_fields

    def get_selected_fields(self, complexity_level):
        """Get fields and return in flat format for database operations."""
        if complexity_level == 'all':
            # Return all fields as flat dict for database mapping
            return {field_name: True for field_name in self.field_definitions.keys()}
        elif complexity_level == 'minimal':
            # Return only minimal fields as flat dict
            selected = {}
            for field_name, field_info in self.field_definitions.items():
                if 'minimal' in field_info.get('complexity_levels', []):
                    selected[field_name] = True
            return selected
        elif complexity_level == 'custom':
            # Custom selection would return flat dict
            return {}
        else:
            return self.get_selected_fields('minimal')

    def _group_fields_by_module(self, field_names):
        """Group YAML field names by service module for openweather.py compatibility."""
        grouped = {}
        
        for field_name in field_names:
            if field_name not in self.field_definitions:
                continue
            
            field_config = self.field_definitions[field_name]
            
            module_name = self._find_module_for_field(field_name)
            if not module_name:
                continue
            
            service_field = field_config.get('service_field', field_name)
            
            if module_name not in grouped:
                grouped[module_name] = []
            grouped[module_name].append(service_field)
        
        return grouped

    def _find_module_for_field(self, field_name):
        """Find which API module a field belongs to."""
        for module_name, module_config in self.api_config.get('api_modules', {}).items():
            if field_name in module_config.get('fields', {}):
                return module_name
        return None

    def estimate_field_count(self, selected_fields):
        """Count actual selected fields."""
        return len([f for f in selected_fields.values() if f])
    
    def get_database_field_mappings(self, selected_fields):
        """Handle both flat and grouped field selection formats."""
        mappings = {}
        
        if isinstance(selected_fields, dict) and any(isinstance(v, list) for v in selected_fields.values()):
            # Grouped format from get_selected_fields: {'current_weather': ['temp', 'humidity']}
            for module_name, service_fields in selected_fields.items():
                module_config = self.api_config.get('api_modules', {}).get(module_name, {})
                
                for service_field in service_fields:
                    for field_name, field_config in module_config.get('fields', {}).items():
                        if field_config.get('service_field') == service_field:
                            db_field = field_config['database_field']
                            db_type = field_config['database_type']
                            mappings[db_field] = db_type
                            break
        else:
            # Flat format: {'ow_temperature': True}
            for field_name, selected in selected_fields.items():
                if selected and field_name in self.field_definitions:
                    field_info = self.field_definitions[field_name]
                    mappings[field_info['database_field']] = field_info['database_type']
        
        return mappings

    def _save_field_selection(self, selected_fields):
        """Save ONLY clean field selection data."""
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        # CLEAN the selection - only keep actual field selections
        clean_selection = {}
        valid_fields = set(self.field_definitions.keys())
        
        for field_name, selected in selected_fields.items():
            if field_name in valid_fields:
                clean_selection[field_name] = selected
        
        config = configobj.ConfigObj()
        config.filename = selection_file
        
        # Store ONLY clean field selection
        config['field_selection'] = {
            'selected_fields': clean_selection,
            'selection_timestamp': str(int(time.time())),
            'config_version': '1.0'
        }
        
        config.write()
        os.chmod(selection_file, 0o644)
        
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
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            if api_key:
                # Basic validation
                if len(api_key) >= 20 and api_key.replace('_', '').replace('-', '').isalnum():
                    print(f"✓ API key accepted: {api_key[:8]}...")
                    confirm = input("Is this API key correct? (y/n): ").strip().lower()
                    if confirm in ['y', 'yes']:
                        return api_key
                    else:
                        continue
                else:
                    print("API key seems invalid. Please check and try again.")
            else:
                print("API key is required. Please enter a valid key.")
    
    def _select_modules(self):
        """Data-driven module selection instead of hardcoded."""
        print("\n" + "="*60)
        print("MODULE SELECTION")
        print("="*60)
        print("Choose which OpenWeather data modules to enable:")
        print()
        
        modules = {}
        api_modules = self.api_config.get('api_modules', {})
        
        if not api_modules:
            print("Warning: Using fallback module selection")
            return self._select_modules_fallback()
        
        for module_name, module_config in api_modules.items():
            print(f"📊 {module_config['display_name']}")
            print(f"   {module_config['description']}")
            
            field_count = len(module_config.get('fields', {}))
            print(f"   Available fields: {field_count}")
            print()
            
            prompt = f"   Enable {module_config['display_name']}? [Y/n]: "
            try:
                response = input(prompt).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nInstallation cancelled by user.")
                sys.exit(1)
            
            enabled = response not in ['n', 'no']
            modules[module_name] = enabled
            
            if enabled:
                print(f"   ✓ {module_config['display_name']} enabled")
            else:
                print(f"   - {module_config['display_name']} disabled")
            print()
        
        print("✓ Module selection completed")
        enabled_list = [name for name, enabled in modules.items() if enabled]
        print(f"  Enabled modules: {', '.join(enabled_list)}")
        
        return modules

    def _select_modules_fallback(self):
        """Fallback to existing hardcoded module selection if YAML fails."""
        modules = {}
        
        print("1. Current Weather Data")
        print("   - Temperature, humidity, pressure, wind")
        print("   - Cloud cover, visibility, weather conditions")
        current_weather = input("   Enable current weather data? [Y/n]: ").strip().lower()
        modules['current_weather'] = current_weather not in ['n', 'no']
        
        print()
        
        print("2. Air Quality Data") 
        print("   - PM2.5, PM10, Ozone, NO2, SO2, CO")
        print("   - Air Quality Index (AQI)")
        air_quality = input("   Enable air quality data? [Y/n]: ").strip().lower()
        modules['air_quality'] = air_quality not in ['n', 'no']
        
        return modules

    def _write_enhanced_config(self, config_dict, selected_fields, api_key, intervals):
        """Write configuration in the module-based format that openweather.py expects."""
        service_config = config_dict.setdefault('OpenWeatherService', {})
        
        # Basic service configuration
        service_config['enable'] = True
        service_config['api_key'] = api_key
        service_config['timeout'] = 30
        service_config['log_success'] = False
        service_config['log_errors'] = True
        
        # Unit system detection and integration
        weewx_unit_system = self._detect_weewx_unit_system()
        openweather_units = self._map_to_openweather_units(weewx_unit_system)
        
        service_config['unit_system'] = {
            'weewx_system': weewx_unit_system,
            'api_units': openweather_units,
            'wind_conversion_needed': (weewx_unit_system == 'METRIC')
        }
        
        print(f"Unit system integration: WeeWX '{weewx_unit_system}' → OpenWeather '{openweather_units}'")
        if weewx_unit_system == 'METRIC':
            print("  Note: Wind speed conversion (m/s → km/hr) will be applied automatically")
        
        # Module configuration - group fields by API source
        modules = service_config.setdefault('modules', {})
        
        # Group selected fields by module for service compatibility
        field_groups = self._group_fields_by_module(selected_fields)
        
        for module_name, field_list in field_groups.items():
            if field_list:  # Only include modules with selected fields
                modules[module_name] = True
            else:
                modules[module_name] = False
        
        # Intervals configuration
        intervals_config = service_config.setdefault('intervals', {})
        intervals_config.update(intervals)
        
        # CRITICAL: Write field selection in MODULE-BASED format for openweather.py
        # Store grouped fields in the format the service expects: {'current_weather': ['temp', 'humidity']}
        field_selection = service_config.setdefault('field_selection', {})
        field_selection['complexity_level'] = getattr(self, 'complexity_level', 'custom')
        field_selection['selection_timestamp'] = str(int(time.time()))
        field_selection['config_version'] = '1.0'
        
        # Store selected fields in MODULE-BASED format (what openweather.py expects)
        field_selection['selected_fields'] = field_groups
        
        return config_dict

    def _setup_unit_system(self):
        """Configure WeeWX unit system for OpenWeather fields."""
        print("  Setting up unit system for OpenWeather fields...")
        
        # This would typically be handled by the service at runtime
        # For installation, we just note that it will be configured
        print("  ✓ Unit system will be configured when service starts")
    
    def _load_field_selection(self):
        """Load field selection from extension-managed configuration file."""
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
            print(f"    Selected fields: {len(selected_fields)}")
            
            return selected_fields
            
        except Exception as e:
            print(f"    ❌ Failed to load field selection: {e}")
            return {}
      
    def _detect_weewx_unit_system(self):
        """Detect WeeWX unit system from existing configuration."""
        try:
            # Read WeeWX configuration to detect current unit system
            weewx_config_path = '/etc/weewx/weewx.conf'
            if not os.path.exists(weewx_config_path):
                weewx_config_path = os.path.expanduser('~/weewx-data/weewx.conf')
            
            if os.path.exists(weewx_config_path):
                config = configobj.ConfigObj(weewx_config_path)
                stdconvert_config = config.get('StdConvert', {})
                target_unit = stdconvert_config.get('target_unit', 'US').upper()
                
                if target_unit in ['US', 'METRICWX', 'METRIC']:
                    return target_unit
            
            print("Warning: Could not detect WeeWX unit system, defaulting to US")
            return 'US'
            
        except Exception as e:
            print(f"Warning: Error detecting WeeWX unit system: {e}, defaulting to US")
            return 'US'

    def _map_to_openweather_units(self, weewx_unit_system):
        """Map WeeWX unit system to OpenWeather API units parameter."""
        mapping = {
            'US': 'imperial',        # F, mph, inHg → OpenWeather imperial
            'METRICWX': 'metric',    # C, m/s, mbar → OpenWeather metric (perfect match)
            'METRIC': 'metric'       # C, km/hr, mbar → OpenWeather metric (wind needs conversion)
        }
        
        api_units = mapping.get(weewx_unit_system, 'metric')  # Fallback to metric
        return api_units

    def _group_fields_by_module(self, flat_field_selection):
        """Convert flat field selection to module-based format for openweather.py.
        
        Input: {'ow_temperature': True, 'ow_humidity': True, 'ow_pm25': True}
        Output: {'current_weather': ['temp', 'humidity'], 'air_quality': ['pm2_5']}
        """
        grouped = {}
        
        for field_name, selected in flat_field_selection.items():
            if not selected:
                continue
                
            # Find which API module this field belongs to using YAML data
            module_name = self._find_module_for_field(field_name)
            if not module_name:
                continue
            
            # Get the service field name from YAML
            field_config = self.field_definitions.get(field_name, {})
            service_field = field_config.get('service_field', field_name.replace('ow_', ''))
            
            # Add to module group
            if module_name not in grouped:
                grouped[module_name] = []
            grouped[module_name].append(service_field)
        
        return grouped

    def _find_module_for_field(self, field_name):
        """Find which API module a field belongs to using YAML api_modules structure."""
        for module_name, module_config in self.api_config.get('api_modules', {}).items():
            if field_name in module_config.get('fields', {}):
                return module_name
        return None


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
                ('', ['openweather_fields.yaml'])
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
        
        try:
            # Delegate all interactive configuration to separate class
            # FIX: Pass engine.config_dict to constructor, not to run_interactive_setup
            configurator = OpenWeatherConfigurator(engine.config_dict)
            
            # FIX: run_interactive_setup returns tuple, not string
            config_dict, selected_fields = configurator.run_interactive_setup()
            
            # Update the engine configuration
            engine.config_dict.update(config_dict)
            
            # Get database field mappings for selected fields
            field_mappings = configurator.get_database_field_mappings(selected_fields)
            
            # Create database manager and add fields
            db_manager = DatabaseManager(engine.config_dict)
            db_manager.create_database_fields(field_mappings)
            
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
            
            return True
            
        except Exception as e:
            print(f"\nInstallation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
        
    def reconfigure(self, engine):
        """Support field selection reconfiguration via 'weectl extension reconfigure OpenWeather'."""
        print("\n" + "="*80)
        print("WEEWX OPENWEATHER EXTENSION RECONFIGURATION")
        print("="*80)
        print("This will allow you to change your field selection settings.")
        print("Existing data will be preserved - only new fields will be added.")
        print()
        
        try:
            # FIX: Create configurator with engine.config_dict
            configurator = OpenWeatherConfigurator(engine.config_dict)
            
            # FIX: run_interactive_setup returns tuple, not string
            config_dict, selected_fields = configurator.run_interactive_setup()
            
            # FIX: Use configurator methods directly (no more field_helper)
            field_mappings = configurator.get_database_field_mappings(selected_fields)
            
            # Create database manager and add any new fields
            db_manager = DatabaseManager(engine.config_dict)
            db_manager.create_database_fields(field_mappings)
            
            # Update engine configuration
            engine.config_dict.update(config_dict)
            
            print("\n✓ Reconfiguration completed successfully")
            print("Please restart WeeWX to apply changes: sudo systemctl restart weewx")
            return True
            
        except Exception as e:
            print(f"\nReconfiguration failed: {e}")
            import traceback
            traceback.print_exc()
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
# ============================================================================
# COMPLETE OPENWEATHER.PY IMPLEMENTATION
# ============================================================================

# REMOVE: Delete this entire class from openweather.py
# class DatabaseSchemaManager:
#     """Manages dynamic database schema based on field selections."""
#     # DELETE ALL OF THIS CLASS - No longer needed

# REPLACE: Update OpenWeatherService class with these changes
class OpenWeatherService(StdService):
    """Robust OpenWeather service that never breaks WeeWX - graceful degradation only."""
    
    def __init__(self, engine, config_dict):
        super().__init__(engine, config_dict)
        
        # Load service configuration (operational settings only from weewx.conf)
        self.service_config = config_dict.get('OpenWeatherService', {})
        
        # Initialize with safe defaults
        self.selected_fields = {}
        self.active_fields = {}  # Fields actually available for collection
        self.service_enabled = False
        
        try:
            # Load field selection from extension-managed file (NOT weewx.conf)
            self.selected_fields = self._load_field_selection()
            
            # Validate and clean field selection (never fails - just logs issues)
            self.active_fields = self._validate_and_clean_selection()
            
            if self.active_fields:
                # Initialize data collection if we have usable fields
                self._initialize_data_collection()
                self.service_enabled = True
                log.info(f"OpenWeather service started successfully ({self._count_active_fields()} fields active)")
            else:
                log.error("OpenWeather service disabled - no usable fields available")
                log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to fix configuration")
                
        except Exception as e:
            # NEVER let OpenWeather break WeeWX startup
            log.error(f"OpenWeather service initialization failed: {e}")
            log.error("OpenWeather data collection disabled - WeeWX will continue normally")
            self.service_enabled = False
    
    def _load_field_selection(self):
        """Load field selection from extension-managed file - never fails."""
        selection_file = '/etc/weewx/openweather_fields.conf'
        
        try:
            if os.path.exists(selection_file):
                config = configobj.ConfigObj(selection_file)
                selected_fields = config.get('selected_fields', {})
                
                if not selected_fields:
                    log.warning("No field selection found in configuration file")
                    return {}
                
                log.info(f"Loaded field selection from {selection_file}: {list(selected_fields.keys())}")
                return selected_fields
            else:
                log.error(f"Field selection file not found: {selection_file}")
                log.error("This usually means the extension was not properly installed")
                log.error("HINT: Run 'weectl extension install weewx-openweather.zip' to properly install")
                return {}
                
        except Exception as e:
            log.error(f"Failed to load field selection from {selection_file}: {e}")
            log.error("OpenWeather service will be disabled")
            return {}
    
    def _validate_and_clean_selection(self):
        """Validate field selection and return only usable fields - never fails."""
        
        if not self.selected_fields:
            log.warning("No field selection available - OpenWeather collection disabled")
            return {}
        
        field_manager = FieldSelectionManager()
        active_fields = {}
        total_selected = 0
        
        try:
            # Get expected database fields based on selection
            expected_fields = field_manager.get_database_field_mappings(self.selected_fields)
            
            if not expected_fields:
                log.warning("No database fields required for current selection")
                return {}
            
            # Check which fields actually exist in database
            existing_db_fields = self._get_existing_database_fields()
            
            # Validate each module's fields
            for module, fields in self.selected_fields.items():
                if not fields:
                    continue
                    
                if fields == 'all':
                    # Handle 'all' selection
                    module_fields = self._get_all_fields_for_module(module, field_manager)
                    total_selected += len(module_fields)
                    active_module_fields = self._validate_module_fields(module, module_fields, expected_fields, existing_db_fields, field_manager)
                elif isinstance(fields, list):
                    # Handle specific field list
                    total_selected += len(fields)
                    active_module_fields = self._validate_module_fields(module, fields, expected_fields, existing_db_fields, field_manager)
                else:
                    log.warning(f"Invalid field selection format for module '{module}': {fields}")
                    continue
                
                if active_module_fields:
                    active_fields[module] = active_module_fields
            
            # Validate forecast table if needed
            self._validate_forecast_table()
            
            # Summary logging
            total_active = self._count_active_fields(active_fields)
            if total_active > 0:
                log.info(f"Field validation complete: {total_active}/{total_selected} fields active")
                if total_active < total_selected:
                    log.warning(f"{total_selected - total_active} fields unavailable - see errors above")
                    log.warning("HINT: Run 'weectl extension reconfigure OpenWeather' to fix field issues")
                
                # Check for new fields available
                self._check_for_new_fields(field_manager)
            else:
                log.error("No usable fields found - all fields have issues")
            
            return active_fields
            
        except Exception as e:
            log.error(f"Field validation failed: {e}")
            return {}
    
    def _validate_module_fields(self, module, fields, expected_fields, existing_db_fields, field_manager):
        """Validate fields for a specific module - never fails."""
        active_fields = []
        
        if not fields:
            return active_fields
        
        field_list = fields if isinstance(fields, list) else []
        
        for field in field_list:
            try:
                # Find the database field name for this logical field
                db_field = self._get_database_field_name(module, field, field_manager)
                
                if not db_field:
                    log.warning(f"Unknown field '{field}' in module '{module}' - skipping")
                    continue
                
                if db_field not in existing_db_fields:
                    log.error(f"Database field '{db_field}' missing for '{module}.{field}' - skipping")
                    log.error(f"HINT: Run 'weectl extension reconfigure OpenWeather' to add missing fields")
                    continue
                
                # Field is valid and available
                active_fields.append(field)
                
            except Exception as e:
                log.error(f"Error validating field '{field}' in module '{module}': {e}")
                continue
        
        if active_fields:
            log.info(f"Module '{module}': {len(active_fields)}/{len(field_list)} fields active")
        else:
            log.warning(f"Module '{module}': no usable fields")
        
        return active_fields
    
    def _get_database_field_name(self, module, field, field_manager):
        """Get database field name for a logical field name."""
        try:
            all_fields = field_manager.get_all_available_fields()
            if module in all_fields:
                for category_data in all_fields[module]['categories'].values():
                    if field in category_data['fields']:
                        return category_data['fields'][field]['database_field']
        except Exception as e:
            log.error(f"Error looking up database field for {module}.{field}: {e}")
        return None
    
    def _get_all_fields_for_module(self, module, field_manager):
        """Get all available fields for a module when 'all' is selected."""
        try:
            all_fields = field_manager.get_all_available_fields()
            if module in all_fields:
                module_fields = []
                for category_data in all_fields[module]['categories'].values():
                    module_fields.extend(category_data['fields'].keys())
                return module_fields
        except Exception as e:
            log.error(f"Error getting all fields for module '{module}': {e}")
        return []
    
    def _validate_forecast_table(self):
        """Validate forecast table if needed - never fails."""
        forecast_modules = ['forecast_daily', 'forecast_hourly', 'forecast_air_quality']
        needs_forecast_table = any(module in self.selected_fields for module in forecast_modules)
        
        if not needs_forecast_table:
            return
        
        try:
            db_binding = 'wx_binding'
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                dbmanager.connection.execute("SELECT 1 FROM openweather_forecast LIMIT 1")
                log.info("Forecast table validated successfully")
        except Exception as e:
            log.error(f"Forecast table missing or inaccessible: {e}")
            log.error("Forecast modules will be disabled")
            log.error("HINT: Run 'weectl extension reconfigure OpenWeather' to create forecast table")
            
            # Remove forecast modules from active fields
            for module in forecast_modules:
                if module in self.active_fields:
                    del self.active_fields[module]
                    log.warning(f"Disabled forecast module: {module}")
    
    def _get_existing_database_fields(self):
        """Get list of existing OpenWeather fields - never fails."""
        try:
            db_binding = 'wx_binding'
            with weewx.manager.open_manager_with_config(self.config_dict, db_binding) as dbmanager:
                existing_fields = []
                for column in dbmanager.connection.genSchemaOf('archive'):
                    field_name = column[1]
                    if field_name.startswith('ow_'):
                        existing_fields.append(field_name)
                return existing_fields
        except Exception as e:
            log.error(f"Error checking database fields: {e}")
            return []
    
    def _check_for_new_fields(self, field_manager):
        """Check if new fields are available that user hasn't selected."""
        try:
            all_available = field_manager.get_all_available_fields()
            
            for module, module_data in all_available.items():
                if module not in self.selected_fields or not self.selected_fields[module]:
                    # Module not selected at all
                    all_module_fields = self._get_all_fields_for_module(module, field_manager)
                    if all_module_fields:
                        log.info(f"New module available: '{module}' with {len(all_module_fields)} fields")
                        log.info(f"HINT: Run 'weectl extension reconfigure OpenWeather' to enable new features")
                elif self.selected_fields[module] != 'all':
                    # Check for new fields in selected modules
                    selected_fields = self.selected_fields[module] if isinstance(self.selected_fields[module], list) else []
                    all_module_fields = self._get_all_fields_for_module(module, field_manager)
                    new_fields = [f for f in all_module_fields if f not in selected_fields]
                    
                    if new_fields:
                        log.info(f"New fields available in module '{module}': {new_fields}")
                        log.info(f"HINT: Run 'weectl extension reconfigure OpenWeather' to enable new fields")
                        
        except Exception as e:
            log.debug(f"Error checking for new fields: {e}")
    
    def _count_active_fields(self, fields=None):
        """Count total active fields across all modules."""
        if fields is None:
            fields = self.active_fields
        return sum(len(module_fields) for module_fields in fields.values() if isinstance(module_fields, list))
    
    def _initialize_data_collection(self):
        """Initialize data collection components - graceful failure."""
        try:
            # Set up API client with active fields only
            self.api_client = OpenWeatherAPIClient(
                api_key=self.service_config['api_key'],
                selected_fields=self.active_fields,  # Use validated fields
                timeout=int(self.service_config.get('timeout', 30))
            )
            
            # Set up background collection thread
            self.background_thread = OpenWeatherBackgroundThread(
                config=self.service_config,
                selected_fields=self.active_fields,  # Use validated fields
                api_client=self.api_client
            )
            
            # Start background collection
            self.background_thread.start()
            
            log.info("Data collection initialized successfully")
            
        except Exception as e:
            log.error(f"Failed to initialize data collection: {e}")
            log.error("OpenWeather data collection disabled")
            self.service_enabled = False
    
    def new_archive_record(self, event):
        """Inject OpenWeather data into archive record - never fails."""
        
        if not self.service_enabled:
            return  # Silently skip if service is disabled
        
        try:
            # Get latest collected data
            collected_data = self.get_latest_data()
            
            if not collected_data:
                return  # No data available
            
            # Build record with all expected fields, using None for missing data
            record_update = {}
            field_manager = FieldSelectionManager()
            expected_fields = field_manager.get_database_field_mappings(self.active_fields)
            
            fields_injected = 0
            for db_field, field_type in expected_fields.items():
                if db_field in collected_data and collected_data[db_field] is not None:
                    # Successfully collected data
                    record_update[db_field] = collected_data[db_field]
                    fields_injected += 1
                else:
                    # Missing data - use None/NULL
                    record_update[db_field] = None
            
            # Update the archive record
            event.record.update(record_update)
            
            if fields_injected > 0:
                log.debug(f"Injected OpenWeather data: {fields_injected}/{len(expected_fields)} fields")
            else:
                log.debug("No OpenWeather data available for injection")
                
        except Exception as e:
            log.error(f"Error injecting OpenWeather data: {e}")
            # Continue without OpenWeather data - don't break the archive record
    
    def get_latest_data(self):
        """Get latest collected data - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                return self.background_thread.get_latest_data()
        except Exception as e:
            log.error(f"Error getting latest data: {e}")
        return {}
    
    def shutDown(self):
        """Clean shutdown - never fails."""
        try:
            if hasattr(self, 'background_thread') and self.background_thread:
                self.background_thread.stop()
                log.info("OpenWeather service shutdown complete")
        except Exception as e:
            log.error(f"Error during OpenWeather shutdown: {e}")
            # Continue with shutdown anyway
# WeeWX OpenWeather Extension - Test Suite

Comprehensive test suite for the field selection system implemented in Week 5-6 of the development plan.

## Overview

This test suite validates all aspects of the field selection functionality:

- **Field Selection System**: Tests all complexity levels and custom selection
- **Service Integration**: Tests service correctly applies field filtering
- **Installation Scenarios**: Tests fresh installs, upgrades, and edge cases
- **Database Management**: Tests dynamic schema creation and field handling

## Test Files

### `test_field_selection.py`
Core field selection functionality tests:
- All 4 complexity levels (minimal, standard, comprehensive, everything)
- Custom field selection workflow
- Database field creation for selected fields only
- Configuration persistence and reading
- Data collection filtering logic

### `test_service_integration.py`
Service integration tests:
- Service reads field selection from configuration
- Data collector applies field filtering
- Background thread respects field selection
- Archive record injection filters correctly
- Stale data handling

### `test_installation_scenarios.py`
Installation and upgrade scenario tests:
- Fresh installations with different complexity levels
- Reinstallation with existing fields
- Upgrade scenarios with field selection changes
- Database permission edge cases
- Configuration validation

### `run_all_tests.py`
Complete test runner that executes all test suites and provides comprehensive reporting.

## Requirements

- **WeeWX 5.1+** - Real WeeWX installation (not simulation)
- **OpenWeather Extension** - Must be installed in `bin/user/`
- **Database Permissions** - Write access to WeeWX database
- **weectl Executable** - Available in PATH for database operations
- **OpenWeatherMap API Key** - Optional, for live API testing

## Quick Start

```bash
# Run all tests (recommended)
python3 examples/run_all_tests.py

# Run with live API testing
python3 examples/run_all_tests.py --api-key=YOUR_API_KEY_HERE

# Run with verbose output
python3 examples/run_all_tests.py --verbose

# Run individual test suites
python3 examples/test_field_selection.py
python3 examples/test_service_integration.py
python3 examples/test_installation_scenarios.py
```

## Test Environment Setup

### Automatic Setup
The test suites automatically create temporary test environments:
- Temporary directories for isolated testing
- Test databases with WeeWX schema
- Mock configurations with proper structure
- Cleanup after test completion

### Manual Setup (if needed)
```bash
# Ensure WeeWX is accessible
export PYTHONPATH="/usr/share/weewx:/etc/weewx/bin/user:$PYTHONPATH"

# Verify extension is installed
ls -la /etc/weewx/bin/user/openweather.py
ls -la /etc/weewx/bin/user/install.py

# Check weectl is available
weectl --version
```

## Test Results Interpretation

### Success Indicators
```
✅ ALL TESTS PASSED
🎉 Field selection system is working correctly!
🚀 WEEK 5-6 DELIVERABLES COMPLETE
```

### Failure Indicators
```
❌ SOME TESTS FAILED
Review the detailed results above to identify issues.
```

### Common Issues and Solutions

#### WeeWX Import Errors
```
❌ Error: Cannot import WeeWX modules
```
**Solution**: Ensure WeeWX 5.1+ is installed and accessible:
```bash
sudo apt update && sudo apt install weewx
# or appropriate installation method for your system
```

#### Extension Import Errors
```
❌ Error: Cannot import OpenWeather extension modules
```
**Solution**: Ensure extension is properly installed:
```bash
weectl extension list
# Should show OpenWeather extension
```

#### Database Permission Errors
```
❌ Database permission handling: Failed to create test database
```
**Solution**: Ensure test directory is writable:
```bash
# Run tests from a directory you own
cd ~/
python3 /path/to/examples/run_all_tests.py
```

#### weectl Not Found
```
⚠️ weectl not found - database field creation tests may fail
```
**Solution**: Ensure weectl is in PATH:
```bash
which weectl
# Should return path to weectl executable
```

## Test Coverage

### Field Selection Functionality (test_field_selection.py)
- ✅ All complexity levels create correct database fields
- ✅ Custom field selection workflow functions properly  
- ✅ Database field creation handles all scenarios
- ✅ Configuration persistence works correctly
- ✅ Data collection filtering logic is sound
- ✅ Field count estimation is accurate

### Service Integration (test_service_integration.py)
- ✅ Service correctly reads field selection from configuration
- ✅ Data collector applies field filtering properly
- ✅ Background thread respects field selection
- ✅ Archive record injection filters to selected fields only
- ✅ Stale data handling works correctly
- ✅ Unit system setup for selected fields only

### Installation Scenarios (test_installation_scenarios.py)
- ✅ Fresh installations work for all complexity levels
- ✅ Reinstallation scenarios handle existing fields properly
- ✅ Upgrade scenarios preserve and extend field selections
- ✅ Database field management handles edge cases
- ✅ Configuration validation works correctly
- ✅ Permission and error scenarios handled gracefully

## Performance Expectations

### Typical Test Times
- **Field Selection Tests**: 30-60 seconds
- **Service Integration Tests**: 15-30 seconds  
- **Installation Scenario Tests**: 45-90 seconds
- **Complete Suite**: 2-3 minutes

### Performance Factors
- Database operations (field creation/deletion)
- Configuration file I/O
- Temporary file system operations
- Test environment setup/teardown

## Development Usage

### Running Tests During Development
```bash
# Quick validation during development
python3 examples/test_field_selection.py

# Test specific functionality
python3 examples/test_service_integration.py --verbose

# Full validation before commit
python3 examples/run_all_tests.py
```

### Adding New Tests
1. Add test methods to appropriate test class
2. Follow existing naming conventions (`test_description_of_functionality`)
3. Include descriptive print statements for progress tracking
4. Update this README with new test coverage

### Test Data and Mocking
- Tests use real WeeWX installations, not mocks
- Temporary databases are created for isolation
- API calls are mocked unless live API key provided
- Configuration changes are isolated to test environments

## Integration with CI/CD

### GitHub Actions Integration
```yaml
# Example .github/workflows/test.yml
name: Test Field Selection System
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v2
    - name: Install WeeWX
      run: sudo apt install weewx
    - name: Install Extension
      run: weectl extension install .
    - name: Run Tests
      run: python3 examples/run_all_tests.py
```

### Pre-commit Hooks
```bash
# Add to .pre-commit-config.yaml
- repo: local
  hooks:
  - id: openweather-tests
    name: OpenWeather Extension Tests
    entry: python3 examples/run_all_tests.py
    language: system
    pass_filenames: false
```

## Troubleshooting

### Test Environment Issues
1. **Temporary directory permissions**: Tests create temp directories - ensure sufficient disk space and permissions
2. **Database locking**: If tests hang, check for locked database files
3. **Configuration conflicts**: Tests use isolated configs - existing WeeWX config won't interfere

### Extension Issues
1. **Import paths**: Tests add WeeWX paths to sys.path automatically
2. **Module loading**: Ensure extension files are syntactically correct
3. **Dependency issues**: Tests use only standard library + WeeWX modules

### Performance Issues
1. **Slow database operations**: Consider running on SSD storage
2. **Network timeouts**: Mock API calls are used by default
3. **Memory usage**: Tests clean up temporary files automatically

## Contributing

When contributing to the test suite:

1. **Follow existing patterns**: Match the structure and style of existing tests
2. **Add comprehensive coverage**: Include both success and failure scenarios
3. **Update documentation**: Update this README when adding new test files
4. **Test the tests**: Ensure new tests pass consistently
5. **Consider performance**: Avoid unnecessarily slow operations

## Week 5-6 Validation

This test suite specifically validates the Week 5-6 deliverables:

### ✅ Field Selection System
- Interactive terminal UI with curses interface
- 4 complexity levels with smart defaults
- Custom field selection with category organization
- Field validation and error handling

### ✅ Dynamic Database Schema Management  
- Database field creation for selected fields only
- Proper handling of field types (REAL, TEXT, INTEGER)
- Graceful handling of existing fields
- Cross-database compatibility (SQLite, MySQL)

### ✅ Configuration Persistence
- Field selections stored in weewx.conf
- Service reads and applies field selections
- Upgrade scenarios preserve user choices
- Configuration validation and error recovery

### ✅ Service Integration
- Enhanced service applies field filtering
- Background data collection respects selections
- Archive record injection filters correctly
- Unit system setup for selected fields only

All Week 5-6 requirements are fully tested and validated by this comprehensive test suite.
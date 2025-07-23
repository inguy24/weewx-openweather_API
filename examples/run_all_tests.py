#!/usr/bin/env python3
"""
Complete Test Runner for WeeWX OpenWeather Extension

Runs all test suites for the field selection system:
- Field selection functionality tests
- Service integration tests  
- Installation scenario tests

Usage:
    python3 examples/run_all_tests.py [--api-key=YOUR_KEY] [--verbose]
    
Requirements:
    - Real WeeWX 5.1+ installation
    - OpenWeather extension installed
    - Database write permissions
    - Optional: OpenWeatherMap API key for live tests
"""

import sys
import os
import time
import argparse
from datetime import datetime

# Add paths to find test modules
sys.path.insert(0, os.path.dirname(__file__))

try:
    from test_field_selection import run_test_suite as run_field_selection_tests
    from test_service_integration import run_service_integration_tests
    from test_installation_scenarios import run_installation_scenario_tests
except ImportError as e:
    print(f"❌ Error: Cannot import test modules: {e}")
    print("Ensure all test files are in the examples/ directory")
    sys.exit(1)


def print_header(title):
    """Print formatted header."""
    print("\n" + "="*100)
    print(f"  {title}")
    print("="*100)


def print_section(title):
    """Print formatted section header."""
    print("\n" + "-"*80)
    print(f"  {title}")
    print("-"*80)


def run_complete_test_suite(api_key=None, verbose=False):
    """Run all test suites and provide comprehensive summary."""
    
    start_time = time.time()
    
    print_header("WEEWX OPENWEATHER EXTENSION - COMPLETE TEST SUITE")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Test Environment: Real WeeWX installation")
    if api_key:
        print(f"API Key: {api_key[:8]}... (provided for live tests)")
    else:
        print("API Key: Not provided (mock testing only)")
    print(f"Verbose Mode: {'Enabled' if verbose else 'Disabled'}")
    
    # Test results tracking
    test_results = {}
    
    print_section("TEST SUITE 1: FIELD SELECTION FUNCTIONALITY")
    print("Testing field selection system components:")
    print("• All complexity levels (minimal, standard, comprehensive, everything)")
    print("• Custom field selection workflow")
    print("• Database field creation for selected fields only")
    print("• Configuration persistence and service reading")
    print("• Data collection filtering")
    print()
    
    try:
        suite1_start = time.time()
        success1 = run_field_selection_tests()
        suite1_time = time.time() - suite1_start
        
        test_results['field_selection'] = {
            'success': success1,
            'duration': suite1_time,
            'description': 'Field Selection Functionality'
        }
        
        print(f"\n⏱️  Field Selection Tests completed in {suite1_time:.1f} seconds")
        
    except Exception as e:
        print(f"❌ Field Selection Tests failed with exception: {e}")
        test_results['field_selection'] = {
            'success': False,
            'duration': 0,
            'description': 'Field Selection Functionality',
            'error': str(e)
        }
    
    print_section("TEST SUITE 2: SERVICE INTEGRATION")
    print("Testing service integration with field selection:")
    print("• Service correctly reads field selection from configuration")
    print("• Data collector applies field filtering properly")
    print("• Background thread respects field selection")
    print("• Archive record injection filters to selected fields only")
    print("• Stale data handling")
    print()
    
    try:
        suite2_start = time.time()
        success2 = run_service_integration_tests(api_key)
        suite2_time = time.time() - suite2_start
        
        test_results['service_integration'] = {
            'success': success2,
            'duration': suite2_time,
            'description': 'Service Integration'
        }
        
        print(f"\n⏱️  Service Integration Tests completed in {suite2_time:.1f} seconds")
        
    except Exception as e:
        print(f"❌ Service Integration Tests failed with exception: {e}")
        test_results['service_integration'] = {
            'success': False,
            'duration': 0,
            'description': 'Service Integration',
            'error': str(e)
        }
    
    print_section("TEST SUITE 3: INSTALLATION SCENARIOS")
    print("Testing installation and upgrade scenarios:")
    print("• Fresh installations with different complexity levels")
    print("• Reinstallation scenarios with existing fields")
    print("• Upgrade scenarios with field selection changes")
    print("• Database field management edge cases")
    print("• Configuration validation")
    print()
    
    try:
        suite3_start = time.time()
        success3 = run_installation_scenario_tests()
        suite3_time = time.time() - suite3_start
        
        test_results['installation_scenarios'] = {
            'success': success3,
            'duration': suite3_time,
            'description': 'Installation Scenarios'
        }
        
        print(f"\n⏱️  Installation Scenario Tests completed in {suite3_time:.1f} seconds")
        
    except Exception as e:
        print(f"❌ Installation Scenario Tests failed with exception: {e}")
        test_results['installation_scenarios'] = {
            'success': False,
            'duration': 0,
            'description': 'Installation Scenarios',
            'error': str(e)
        }
    
    # Calculate overall results
    total_time = time.time() - start_time
    all_successful = all(result['success'] for result in test_results.values())
    successful_suites = sum(1 for result in test_results.values() if result['success'])
    total_suites = len(test_results)
    
    print_header("COMPLETE TEST SUITE RESULTS")
    print(f"Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Duration: {total_time:.1f} seconds ({total_time/60:.1f} minutes)")
    print(f"Suites Passed: {successful_suites}/{total_suites}")
    print()
    
    # Detailed results
    print("DETAILED RESULTS:")
    print("-" * 80)
    for suite_name, result in test_results.items():
        status_icon = "✅" if result['success'] else "❌"
        suite_display = result['description']
        duration = result['duration']
        
        print(f"{status_icon} {suite_display:<35} {duration:>6.1f}s")
        
        if not result['success'] and 'error' in result:
            print(f"    Error: {result['error']}")
    
    print("-" * 80)
    
    if all_successful:
        print("\n🎉 ALL TEST SUITES PASSED!")
        print("\n✅ FIELD SELECTION SYSTEM VALIDATION COMPLETE")
        print("   • All complexity levels work correctly")
        print("   • Custom field selection functions properly")
        print("   • Database field creation handles all scenarios")
        print("   • Service integration works as expected")
        print("   • Installation scenarios are robust")
        print("   • Configuration validation is thorough")
        
        print("\n🚀 WEEK 5-6 DELIVERABLES COMPLETE")
        print("   The field selection system is ready for production use!")
        
    else:
        print("\n❌ SOME TEST SUITES FAILED")
        print("   Review the detailed results above to identify issues.")
        
        failed_suites = [result['description'] for result in test_results.values() if not result['success']]
        print(f"   Failed suites: {', '.join(failed_suites)}")
        
        print("\n🔧 RECOMMENDED ACTIONS:")
        print("   1. Review failed test output for specific issues")
        print("   2. Check WeeWX installation and permissions")
        print("   3. Verify extension files are properly installed")
        print("   4. Ensure database is writable")
        print("   5. Check weectl executable availability")
    
    # Performance summary
    print(f"\n📊 PERFORMANCE SUMMARY:")
    print(f"   Average test suite duration: {total_time/total_suites:.1f} seconds")
    if total_time > 300:  # 5 minutes
        print(f"   ⚠️  Total test time is lengthy ({total_time/60:.1f} minutes)")
        print(f"      Consider running individual test suites for faster feedback")
    else:
        print(f"   ⚡ Good performance - tests completed efficiently")
    
    return all_successful


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(
        description='Run complete test suite for WeeWX OpenWeather field selection system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 run_all_tests.py                           # Run all tests with mocking
  python3 run_all_tests.py --api-key=abc123def456    # Run with live API tests
  python3 run_all_tests.py --verbose                 # Run with verbose output
  python3 run_all_tests.py --help                    # Show this help

Test Suites:
  1. Field Selection Functionality - Tests core field selection system
  2. Service Integration - Tests service reads and applies field selection
  3. Installation Scenarios - Tests installation/upgrade scenarios

Requirements:
  - WeeWX 5.1+ installation
  - OpenWeather extension installed
  - Database write permissions
  - weectl executable available
        """
    )
    
    parser.add_argument(
        '--api-key',
        help='OpenWeatherMap API key for live API testing (optional)',
        metavar='KEY'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output with detailed logging'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='Run quick tests only (skip some longer scenarios)'
    )
    
    args = parser.parse_args()
    
    # Configure logging if verbose
    if args.verbose:
        import logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        print("Verbose logging enabled")
    
    # Validate environment before running tests
    print("Pre-flight environment check...")
    
    # Check for WeeWX
    try:
        import weewx
        print(f"✓ WeeWX found: {weewx.__version__}")
    except ImportError:
        print("❌ WeeWX not found - ensure WeeWX 5.1+ is installed")
        return False
    
    # Check for extension
    try:
        import openweather
        print(f"✓ OpenWeather extension found")
    except ImportError:
        print("❌ OpenWeather extension not found - ensure extension is installed")
        return False
    
    # Check for weectl
    try:
        import subprocess
        result = subprocess.run(['weectl', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            print("✓ weectl executable found")
        else:
            print("⚠️  weectl not working properly - some tests may fail")
    except:
        print("⚠️  weectl not found - database field creation tests may fail")
    
    print("Environment check complete - starting tests...\n")
    
    # Run the complete test suite
    success = run_complete_test_suite(
        api_key=args.api_key,
        verbose=args.verbose
    )
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
#!/bin/bash
#
# WeeWX OpenWeather Extension Package Creator
# Creates installation zip package for WeeWX extension system
#

set -e

VERSION="1.0.0"
EXTENSION_NAME="weewx-openweather"
PACKAGE_NAME="${EXTENSION_NAME}-${VERSION}"
BUILD_DIR="build"
PACKAGE_DIR="${BUILD_DIR}/${EXTENSION_NAME}"

echo "Creating WeeWX OpenWeather Extension Package v${VERSION}"
echo "==========================================================="

# Clean and create build directory
echo "Setting up build directory..."
rm -rf ${BUILD_DIR}
mkdir -p ${PACKAGE_DIR}/bin/user

# Copy required files
echo "Copying extension files..."

# Core files
echo "  Copying install.py..."
cp install.py ${PACKAGE_DIR}/ || { echo "Error: install.py not found"; exit 1; }

echo "  Copying MANIFEST..."
cp MANIFEST ${PACKAGE_DIR}/ || { echo "Error: MANIFEST not found"; exit 1; }

# Service implementation
echo "  Copying bin/user/openweather.py..."
cp bin/user/openweather.py ${PACKAGE_DIR}/bin/user/ || { echo "Error: bin/user/openweather.py not found"; exit 1; }

# Configuration files
echo "  Copying field_selection_defaults.yaml..."
cp field_selection_defaults.yaml ${PACKAGE_DIR}/ || { echo "Error: field_selection_defaults.yaml not found"; exit 1; }

echo "  Copying openweather_fields.yaml..."
cp openweather_fields.yaml ${PACKAGE_DIR}/ || { echo "Error: openweather_fields.yaml not found"; exit 1; }

# Documentation
echo "  Copying README.md..."
cp README.md ${PACKAGE_DIR}/ || { echo "Error: README.md not found"; exit 1; }

echo "  Copying CHANGELOG.md..."
cp CHANGELOG.md ${PACKAGE_DIR}/ || { echo "Error: CHANGELOG.md not found"; exit 1; }

# Verify all files are present
echo "Verifying package contents..."
echo "Required files:"

# Read from the copied MANIFEST file in the package directory
while IFS= read -r file; do
    if [[ ! "$file" =~ ^#.*$ ]] && [[ -n "$file" ]]; then
        if [ -f "${PACKAGE_DIR}/${file}" ]; then
            echo "  ✓ ${file}"
        else
            echo "  ✗ MISSING: ${file}"
            echo "    Expected: ${PACKAGE_DIR}/${file}"
            ls -la "${PACKAGE_DIR}/" 2>/dev/null || echo "    Package directory not found"
            exit 1
        fi
    fi
done < "${PACKAGE_DIR}/MANIFEST"

# Create the zip package
echo ""
echo "Creating installation package..."
cd ${BUILD_DIR}
zip -r ../${PACKAGE_NAME}.zip ${EXTENSION_NAME}/

# Move back and show results
cd ..
PACKAGE_SIZE=$(du -h ${PACKAGE_NAME}.zip | cut -f1)

echo ""
echo "Package created successfully!"
echo "=========================="
echo "Package: ${PACKAGE_NAME}.zip"
echo "Size: ${PACKAGE_SIZE}"
echo ""

# Show package contents
echo "Package contents:"
unzip -l ${PACKAGE_NAME}.zip

echo ""
echo "Installation command:"
echo "  weectl extension install ${PACKAGE_NAME}.zip"
echo ""
echo "The package is ready for distribution!"
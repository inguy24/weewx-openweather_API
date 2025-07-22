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
cp install.py ${PACKAGE_DIR}/
cp MANIFEST ${PACKAGE_DIR}/

# Service implementation
cp bin/user/openweather.py ${PACKAGE_DIR}/bin/user/

# Configuration files
cp field_selection_defaults.yaml ${PACKAGE_DIR}/
cp openweather_fields.yaml ${PACKAGE_DIR}/

# Documentation
cp README.md ${PACKAGE_DIR}/
cp CHANGELOG.md ${PACKAGE_DIR}/

# Verify all files are present
echo "Verifying package contents..."
echo "Required files:"

while IFS= read -r file; do
    if [[ ! "$file" =~ ^#.*$ ]] && [[ -n "$file" ]]; then
        if [ -f "${PACKAGE_DIR}/${file}" ]; then
            echo "  ✓ ${file}"
        else
            echo "  ✗ MISSING: ${file}"
            exit 1
        fi
    fi
done < MANIFEST

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
# How to Set a Custom Plugin Icon for Loupedeck

## Overview

The plugin icon is displayed in the Loupedeck software to represent your plugin. It's configured by placing an icon file in the metadata folder.

## Location

The plugin icon file should be placed at:
```
MouseTronPlugin/src/package/metadata/Icon256x256.png
```

## Icon Requirements

- **File Name**: Must be exactly `Icon256x256.png`
- **Format**: PNG format
- **Size**: 256x256 pixels (recommended)
- **Minimum Size**: 116x116 pixels (will be scaled up)
- **Background**: Transparent or solid color (your choice)

## Steps to Update Your Plugin Icon

1. **Create or prepare your icon image**
   - Design your icon at 256x256 pixels
   - Save it as PNG format
   - Name it `Icon256x256.png`

2. **Replace the existing icon**
   - Navigate to `MouseTronPlugin/src/package/metadata/`
   - Replace the existing `Icon256x256.png` with your new icon
   - Keep the exact same filename

3. **Rebuild the project**
   - The icon is automatically copied during the build process
   - Rebuild your project to include the new icon

4. **Reload the plugin**
   - Restart Loupedeck or reload the plugin
   - Your new icon should appear in the plugin list

## Notes

- The icon file is automatically included in the plugin package during build
- No code changes are needed - just replace the file
- The icon is displayed in the Loupedeck software's plugin manager
- Make sure your icon is recognizable at small sizes (it may be displayed at various sizes)

## Current Icon Location

The current icon is at:
```
MouseTronPlugin/src/package/metadata/Icon256x256.png
```

Simply replace this file with your custom icon to update the plugin icon.


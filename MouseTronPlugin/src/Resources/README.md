# Resources Folder

This folder contains icon images for your plugin actions.

## How to Add Icons

1. **Add your icon files here** (PNG format recommended)
   - Recommended size: 90x90 pixels (or 180x180 for high-res)
   - Use transparent backgrounds for best results
   - Name them descriptively, e.g.:
     - `SendTextIcon.png`
     - `SendTextWithInputIcon.png`
     - `MostRecentActionIcon.png`
     - `MostUsedActionIcon.png`

2. **The project file is already configured** to embed all PNG files in this folder as resources.

3. **In your action classes**, override `GetCommandImage` to load the icon:
   ```csharp
   protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
   {
       try
       {
           return PluginResources.ReadImage("YourIconName.png");
       }
       catch
       {
           return null; // Falls back to default icon
       }
   }
   ```

## Example Icon Files

Place your icon PNG files directly in this folder. The build system will automatically embed them.


# How to Add Custom Icons to Loupedeck Plugin Actions

## Overview

To add custom icons to your Loupedeck plugin actions, you need to:
1. Create a `Resources` folder for your images
2. Add your icon images to the Resources folder
3. Configure the project to embed these images as resources
4. Override the `GetCommandImage` method in your action classes

## Step-by-Step Instructions

### Step 1: Create Resources Folder Structure

Create a `Resources` folder in your `src` directory:
```
MouseTronPlugin/src/Resources/
```

### Step 2: Add Your Icon Images

Place your icon images (PNG format recommended) in the Resources folder. For example:
- `SendTextIcon.png`
- `SendTextWithInputIcon.png`
- `MostRecentActionIcon.png`
- `MostUsedActionIcon.png`

**Recommended icon sizes:**
- 90x90 pixels for standard button icons
- 180x180 pixels for high-resolution displays
- Use PNG format with transparency support

### Step 3: Configure Project File for Embedded Resources

You need to modify `MouseTronPlugin.csproj` to include the images as embedded resources. Add this section:

```xml
<ItemGroup>
  <EmbeddedResource Include="src\Resources\*.png" />
</ItemGroup>
```

Or for a more specific approach:

```xml
<ItemGroup>
  <EmbeddedResource Include="src\Resources\SendTextIcon.png" />
  <EmbeddedResource Include="src\Resources\SendTextWithInputIcon.png" />
  <EmbeddedResource Include="src\Resources\MostRecentActionIcon.png" />
  <EmbeddedResource Include="src\Resources\MostUsedActionIcon.png" />
</ItemGroup>
```

### Step 4: Override GetCommandImage in Your Action Classes

In each action class that inherits from `PluginDynamicCommand`, add a `GetCommandImage` method override:

```csharp
protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
{
    // Load the icon from embedded resources
    // The resource name follows the pattern: Namespace.Resources.Filename
    // For example: "Loupedeck.MouseTronPlugin.Resources.SendTextIcon.png"
    return PluginResources.ReadImage("SendTextIcon.png");
}
```

### Step 5: Handle Different Image Sizes (Optional)

The `PluginImageSize` parameter allows you to return different images for different sizes:

```csharp
protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
{
    // You can return different images based on the requested size
    var imageName = imageSize == PluginImageSize.Width90 
        ? "SendTextIcon.png" 
        : "SendTextIcon@2x.png"; // High-res version
    
    return PluginResources.ReadImage(imageName);
}
```

## Example Implementation

Here's a complete example for the `SendTextAction` class:

```csharp
protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
{
    try
    {
        return PluginResources.ReadImage("SendTextIcon.png");
    }
    catch (Exception ex)
    {
        PluginLog.Error(ex, "Failed to load icon for SendTextAction");
        // Return null to use default icon
        return null;
    }
}
```

## Important Notes

1. **Resource Naming**: The `PluginResources.ReadImage()` method will automatically search for the file in embedded resources. The file name should match what you pass to `ReadImage()`.

2. **Error Handling**: Always wrap icon loading in try-catch. If the icon fails to load, return `null` to use the default icon.

3. **Image Format**: PNG is recommended. The images should have transparent backgrounds for best results.

4. **Rebuild Required**: After adding new resources, you must rebuild the project for them to be embedded.

5. **Resource Path**: The `PluginResources` helper uses the namespace pattern. Make sure your resources are in the correct namespace folder structure.

## Testing

After implementing custom icons:
1. Rebuild the project
2. Reload the plugin in Loupedeck
3. Check that your custom icons appear in the action list

## Troubleshooting

- **Icons not showing**: Check that images are set as "Embedded Resource" in the project file
- **File not found errors**: Verify the file name matches exactly (case-sensitive)
- **Default icons still showing**: Ensure `GetCommandImage` is properly overridden and returns a non-null `BitmapImage`


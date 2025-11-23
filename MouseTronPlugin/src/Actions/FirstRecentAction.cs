namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Threading.Tasks;

    // This class implements a command that sends selected text and user input via POST request
    public class FirstRecentAction : PluginDynamicCommand
    {
        // Default port fallback if server port is not available
        private const Int32 DefaultPort = 8080;
        private const String DefaultPath = "/api/input/";

        private static String com_description = "No recent action";
        private static String com_name = "";
        
        public static void UpdateRecent()
        {
            try
            {
                // Parent directory of MouseTronPlugin
                var parentDirectory = ServerManagementService.ParentDirectory;

                if (parentDirectory != null)
                {
                    var jsonPath = System.IO.Path.Combine(parentDirectory, "recommendations/recent_tool_single_1.json"); // Assuming file name is recent.json
                    PluginLog.Info($"Reading recent action from: {jsonPath}, which exists: {System.IO.File.Exists(jsonPath)}");
                    if (System.IO.File.Exists(jsonPath))
                    {
                        var jsonContent = System.IO.File.ReadAllText(jsonPath);
                        
                        // Simple JSON parsing without external dependencies (System.Text.Json is available in .NET 8)
                        // We are looking for "name" and "description" keys
                        using (var doc = System.Text.Json.JsonDocument.Parse(jsonContent))
                        { 
                            var root = doc.RootElement;
                            // Check if root is an array
                            if (root.ValueKind == System.Text.Json.JsonValueKind.Array)
                            {
                                // Get the first element if the array is not empty
                                if (root.GetArrayLength() > 0)
                                {
                                    var firstItem = root[0];
                                        
                                    if (firstItem.TryGetProperty("tool_name", out var nameElement))
                                    {
                                        if (nameElement.ValueKind == System.Text.Json.JsonValueKind.String)
                                        {
                                            com_name = nameElement.GetString();
                                        }
                                        else
                                        {
                                            com_name = nameElement.ToString();
                                        }
                                    }
                                        
                                    if (firstItem.TryGetProperty("description", out var descElement))
                                    {
                                        if (descElement.ValueKind == System.Text.Json.JsonValueKind.String) 
                                        {
                                            com_description = descElement.GetString();
                                        }
                                        else
                                        {
                                            com_description = descElement.ToString();
                                        }
                                    }
                                }
                                else
                                { 
                                    PluginLog.Warning("JSON array is empty");
                                }
                            } // Fallback: If it WAS an object (legacy support), try parsing directly
                            else if (root.ValueKind == System.Text.Json.JsonValueKind.Object)
                            {
                                if (root.TryGetProperty("tool_name", out var nameElement))
                                {
                                    com_name = nameElement.ValueKind == System.Text.Json.JsonValueKind.String ? nameElement.GetString() : nameElement.ToString();
                                }
                                if (root.TryGetProperty("description", out var descElement))
                                {
                                    com_description = descElement.ValueKind == System.Text.Json.JsonValueKind.String ? descElement.GetString() : descElement.ToString();
                                }
                            }
                            else 
                            {
                                PluginLog.Warning($"Unexpected JSON root type: {root.ValueKind}");
                            }
                        }
                        PluginLog.Info($"Recent name: '{com_name}' and description: '{com_description}'");
                    }
                }
                
            }
            catch (Exception ex)
            {
                // Log error but don't crash
                PluginLog.Warning($"Failed to update recent action: {ex.Message}");
            }
            
        }

        // Initializes the command class.
        public FirstRecentAction()
            : base(displayName: "Most Recent Action", description: "The most recent action done by user", groupName: "HTTP Actions")
        {
            UpdateRecent();
        }

        // This method is called when the user executes the command.
        protected override void RunCommand(String actionParameter)
        {
            // Fire-and-forget async workflow
            _ = this.ExecuteAsync();
        }

        private async Task ExecuteAsync()
        {
            try
            {
                // Show input dialog to get user input (platform-specific)
                var userInput = SystemInfo.ShowInputDialog("Enter Input", $"The most recent action is: {com_description}\n" +
                                                                          $"Please enter additional text:", String.Empty);
                
                // If user cancelled the dialog, return
                if (userInput == null)
                {
                    PluginLog.Info("User cancelled input dialog");
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Normal, "Input cancelled");
                    return;
                }
                
                PluginLog.Info($"Sending selected text: '{com_name}' with user input: '{userInput}'");

                // Get URL from plugin settings or use default
                var postUrl = this.GetPostUrl();
                
                MouseTronPlugin.UpdateAllActions();
                
                // Send POST request with both selected text and user input
                var success = await HttpClientHelper.SendPostRequestWithInputAsync(postUrl, com_name, 
                    "", userInput);

                if (success)
                {
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Normal, "Text and input sent successfully");
                    PluginLog.Info("Text and input sent successfully to localhost");
                }
                else
                {
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Error, "Failed to send text and input to localhost");
                    PluginLog.Warning("Failed to send text and input to localhost");
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, "Error in SendTextWithInputAction");
                this.Plugin.OnPluginStatusChanged(PluginStatus.Error, $"Error: {ex.Message}");
            }
        }

        // Returns the command display name
        protected override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize) =>
            "Most Recent Action";

        // Returns the command icon image
        protected override BitmapImage GetCommandImage(String actionParameter, PluginImageSize imageSize)
        {
            try
            {
                return PluginResources.ReadImage("MostRecentActionIcon.png");
            }
            catch (Exception ex)
            {
                PluginLog.Warning($"Failed to load icon for FirstRecentAction: {ex.Message}");
                return null;
            }
        }

        // Gets the POST URL from plugin settings or uses server port
        private String GetPostUrl()
        {
            // First, try to get URL from plugin settings
            if (this.Plugin.TryGetPluginSetting("InputPostUrl", out var url) && !String.IsNullOrEmpty(url))
            {
                return url;
            }

            // Otherwise, use the server port from ServerManagementService
            var mouseTronPlugin = this.Plugin as MouseTronPlugin;
            var port = mouseTronPlugin?.ServerPort ?? DefaultPort;
            return $"http://localhost:{port}{DefaultPath}";
        }
    }
}


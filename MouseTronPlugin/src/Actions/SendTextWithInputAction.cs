namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Threading.Tasks;

    // This class implements a command that sends selected text and user input via POST request
    public class SendTextWithInputAction : PluginDynamicCommand
    {
        // Default port fallback if server port is not available
        private const Int32 DefaultPort = 8080;
        private const String DefaultPath = "/api/input/";

        // Initializes the command class.
        public SendTextWithInputAction()
            : base(displayName: "Send Text With Input", description: "Sends selected text and user input to localhost", groupName: "HTTP Actions")
        {
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
                // Save current clipboard content
                var originalClipboard = SystemInfo.GetClipboardText();

                // Copy selected text by sending copy keyboard shortcut
                // This uses platform-specific methods (AppleScript on macOS, PowerShell on Windows)
                // since the SDK's SendKeyboardShortcut doesn't support modifier key combinations
                SystemInfo.CopySelectedText(this.Plugin);
                
                // Wait a bit for the copy operation to complete
                await Task.Delay(200);
                
                // Get the selected text from clipboard (now contains the copied selection)
                var selectedText = SystemInfo.GetClipboardText();
                
                // Restore original clipboard if it was different
                if (!String.IsNullOrEmpty(originalClipboard) && originalClipboard != selectedText)
                {
                    var restored = SystemInfo.SetClipboardText(originalClipboard);
                    if (!restored)
                    {
                        PluginLog.Warning("Failed to restore original clipboard content");
                    }
                    else
                    {
                        PluginLog.Info("Original clipboard content restored successfully");
                    }
                }
                
                // If no text was copied, show warning
                if (String.IsNullOrEmpty(selectedText))
                {
                    PluginLog.Info("No text was selected. Please select text first.");
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Warning, "No text selected. Please select text first.");
                    return;
                }

                // Show input dialog to get user input (platform-specific)
                var userInput = SystemInfo.ShowInputDialog("Enter Input", "Please enter additional text:", String.Empty);
                
                // If user cancelled the dialog, return
                if (userInput == null)
                {
                    PluginLog.Info("User cancelled input dialog");
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Normal, "Input cancelled");
                    return;
                }
                
                var applicationName = SystemInfo.GetCurrentApplicationName();
                
                PluginLog.Info($"Sending selected text: '{selectedText}' from application '{applicationName}' with user input: '{userInput}'");

                // Get URL from plugin settings or use default
                var postUrl = this.GetPostUrl();
                
                // Send POST request with both selected text and user input
                var success = await HttpClientHelper.SendPostRequestWithInputAsync(postUrl, selectedText, applicationName, userInput);

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
            "Send Text With Input";

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


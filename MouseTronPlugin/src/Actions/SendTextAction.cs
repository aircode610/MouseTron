namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Runtime.InteropServices;
    using System.Threading.Tasks;

    // This class implements a command that sends selected text and current application name via POST request
    public class SendTextAction : PluginDynamicCommand
    {
        // Default localhost URL - can be configured via plugin settings
        private const String DefaultPostUrl = "http://localhost:8080/api/text";

        // Initializes the command class.
        public SendTextAction()
            : base(displayName: "Send Text", description: "Sends selected text and app name to localhost", groupName: "HTTP Actions")
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

                // Get current application name
                var applicationName = SystemInfo.GetCurrentApplicationName();

                PluginLog.Info($"Sending text: '{selectedText}' from application: '{applicationName}'");

                // Get URL from plugin settings or use default
                var postUrl = this.GetPostUrl();
                // bool success;
                // if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                // {
                //     success = await HttpClientHelper.SendPostRequestAsync(postUrl, "pizda", applicationName);
                // }
                // else
                // {
                //     success = await HttpClientHelper.SendPostRequestAsync(postUrl, "govno", applicationName);
                // }
                // Send POST request
                var success = await HttpClientHelper.SendPostRequestAsync(postUrl, selectedText, applicationName);

                if (success)
                {
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Normal, "Text sent successfully");
                    PluginLog.Info("Text sent successfully to localhost");
                }
                else
                {
                    this.Plugin.OnPluginStatusChanged(PluginStatus.Error, "Failed to send text to localhost");
                    PluginLog.Warning("Failed to send text to localhost");
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, "Error in SendTextAction");
                this.Plugin.OnPluginStatusChanged(PluginStatus.Error, $"Error: {ex.Message}");
            }
        }

        // Returns the command display name
        protected override String GetCommandDisplayName(String actionParameter, PluginImageSize imageSize) =>
            "Send Text";

        // Gets the POST URL from plugin settings or returns default
        private String GetPostUrl()
        {
            if (this.Plugin.TryGetPluginSetting("PostUrl", out var url) && !String.IsNullOrEmpty(url))
            {
                return url;
            }
            return DefaultPostUrl;
        }
    }
}


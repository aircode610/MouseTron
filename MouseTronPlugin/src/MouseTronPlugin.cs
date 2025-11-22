namespace Loupedeck.MouseTronPlugin
{
    using System;

    // This class contains the plugin-level logic of the Loupedeck plugin.

    public class MouseTronPlugin : Plugin
    {
        private ServerManagementService _serverService;
        private ToolsReceiverService _toolsReceiverService;

        // Gets a value indicating whether this is an API-only plugin.
        public override Boolean UsesApplicationApiOnly => true;

        // Gets a value indicating whether this is a Universal plugin or an Application plugin.
        public override Boolean HasNoApplication => true;

        // Gets the server management service
        public ServerManagementService ServerService => this._serverService;

        // Gets the tools receiver service
        public ToolsReceiverService ToolsReceiverService => this._toolsReceiverService;

        // Gets the current server port (null if server is not running)
        public Int32? ServerPort => this._serverService?.ServerPort;

        // Gets the current tools receiver port (null if receiver is not running)
        public Int32? ToolsReceiverPort => this._toolsReceiverService?.ReceiverPort;

        // Initializes a new instance of the plugin class.
        public MouseTronPlugin()
        {
            // Initialize the plugin log.
            PluginLog.Init(this.Log);

            // Initialize the plugin resources.
            PluginResources.Init(this.Assembly);

            // Initialize server management service
            this._serverService = new ServerManagementService(this);
            
            // Initialize tools receiver service
            this._toolsReceiverService = new ToolsReceiverService(this);
        }

        // This method is called when the plugin is loaded.
        public override void Load()
        {
            // Start the tools receiver first (it needs to be ready to receive POSTs)
            if (this._toolsReceiverService != null)
            {
                var receiverStarted = this._toolsReceiverService.Start();
                if (receiverStarted)
                {
                    PluginLog.Info($"Tools receiver started on port {this._toolsReceiverService.ReceiverPort}");
                }
                else
                {
                    PluginLog.Warning("Failed to start tools receiver");
                }
            }
            
            // Start the main server
            if (this._serverService != null)
            {
                var started = this._serverService.Start();
                if (started)
                {
                    PluginLog.Info($"Server started on port {this._serverService.ServerPort}");
                    
                    // Set environment variable so server.py knows where to POST
                    if (this._toolsReceiverService?.ReceiverPort != null)
                    {
                        var toolsUrl = $"http://localhost:{this._toolsReceiverService.ReceiverPort}/api/tools";
                        System.Environment.SetEnvironmentVariable("TOOLS_POST_URL", toolsUrl);
                        PluginLog.Info($"Set TOOLS_POST_URL environment variable to: {toolsUrl}");
                    }
                }
                else
                {
                    PluginLog.Warning("Failed to start server");
                }
            }
        }

        // This method is called when the plugin is unloaded.
        public override void Unload()
        {
            // Stop the tools receiver
            if (this._toolsReceiverService != null)
            {
                this._toolsReceiverService.Stop();
                PluginLog.Info("Tools receiver stopped");
            }
            
            // Stop the server
            if (this._serverService != null)
            {
                this._serverService.Stop();
                PluginLog.Info("Server stopped");
            }

            // Dispose HTTP client
            HttpClientHelper.Dispose();
        }
    }
}

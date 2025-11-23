namespace Loupedeck.MouseTronPlugin
{
    using System;

    // This class contains the plugin-level logic of the Loupedeck plugin.

    public class MouseTronPlugin : Plugin
    {
        public static void UpdateAllActions()
        {
            FirstRecentAction.UpdateRecent();
            FirstMostUsedAction.UpdateRecent();
        }
        
        private ServerManagementService _serverService;

        // Gets a value indicating whether this is an API-only plugin.
        public override Boolean UsesApplicationApiOnly => true;

        // Gets a value indicating whether this is a Universal plugin or an Application plugin.
        public override Boolean HasNoApplication => true;

        // Gets the server management service
        public ServerManagementService ServerService => this._serverService;

        // Gets the current server port (null if server is not running)
        public Int32? ServerPort => this._serverService?.ServerPort;

        // Initializes a new instance of the plugin class.
        public MouseTronPlugin()
        {
            // Initialize the plugin log.
            PluginLog.Init(this.Log);

            // Initialize the plugin resources.
            PluginResources.Init(this.Assembly);

            // Initialize server management service
            this._serverService = new ServerManagementService(this);
        }

        // This method is called when the plugin is loaded.
        public override void Load()
        {
            // Start the server
            if (this._serverService != null)
            {
                var started = this._serverService.Start();
                if (started)
                {
                    PluginLog.Info($"Server started on port {this._serverService.ServerPort}");
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

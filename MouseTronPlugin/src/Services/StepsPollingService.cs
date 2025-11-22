namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Threading.Tasks;
    using System.Timers;

    // Service that polls a localhost endpoint for steps and shows them as notifications
    internal class StepsPollingService
    {
        private readonly Plugin _plugin;
        private Timer _pollingTimer;
        private String _lastSteps = String.Empty;
        private const String DefaultGetUrl = "http://localhost:8080/api/steps";
        private const Int32 DefaultPollingInterval = 2000; // 2 seconds

        public StepsPollingService(Plugin plugin)
        {
            this._plugin = plugin ?? throw new ArgumentNullException(nameof(plugin));
        }

        // Starts the polling service
        public void Start()
        {
            var interval = this.GetPollingInterval();
            var url = this.GetGetUrl();

            PluginLog.Info($"Starting steps polling service. URL: {url}, Interval: {interval}ms");

            this._pollingTimer = new Timer(interval)
            {
                AutoReset = true
            };
            this._pollingTimer.Elapsed += async (sender, e) => await this.OnPollingTimerElapsed();
            this._pollingTimer.Start();

            // Poll immediately on start
            Task.Run(async () => await this.OnPollingTimerElapsed());
        }

        // Stops the polling service
        public void Stop()
        {
            if (this._pollingTimer != null)
            {
                this._pollingTimer.Stop();
                this._pollingTimer.Elapsed -= async (sender, e) => await this.OnPollingTimerElapsed();
                this._pollingTimer.Dispose();
                this._pollingTimer = null;
                PluginLog.Info("Steps polling service stopped");
            }
        }

        // Handles the polling timer elapsed event
        private async Task OnPollingTimerElapsed()
        {
            try
            {
                var url = this.GetGetUrl();
                var steps = await HttpClientHelper.SendGetRequestAsync(url);

                if (steps != null && steps != this._lastSteps)
                {
                    this._lastSteps = steps;
                    
                    // Show notification with the steps
                    this._plugin.OnPluginStatusChanged(PluginStatus.Normal, steps);
                    PluginLog.Info($"Steps updated: {steps}");
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, "Error in steps polling service");
            }
        }

        // Gets the GET URL from plugin settings or returns default
        private String GetGetUrl()
        {
            if (this._plugin.TryGetPluginSetting("GetUrl", out var url) && !String.IsNullOrEmpty(url))
            {
                return url;
            }
            return DefaultGetUrl;
        }

        // Gets the polling interval from plugin settings or returns default
        private Int32 GetPollingInterval()
        {
            if (this._plugin.TryGetPluginSetting("PollingInterval", out var intervalStr) && 
                Int32.TryParse(intervalStr, out var interval))
            {
                return interval;
            }
            return DefaultPollingInterval;
        }
    }
}


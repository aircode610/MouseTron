namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Net.Http;
    using System.Text;
    using System.Text.Json;
    using System.Threading.Tasks;

    // Helper class for making HTTP requests
    internal static class HttpClientHelper
    {
        private static readonly HttpClient _httpClient = new HttpClient
        {
            Timeout = TimeSpan.FromSeconds(10)
        };

        // Sends a POST request to localhost with selected text and application name
        public static async Task<Boolean> SendPostRequestAsync(String url, String selectedText, String applicationName)
        {
            try
            {
                var payload = new
                {
                    selectedText = selectedText ?? String.Empty,
                    applicationName = applicationName ?? "Unknown"
                };

                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync(url, content);
                var responseContent = await response.Content.ReadAsStringAsync();

                if (response.IsSuccessStatusCode)
                {
                    PluginLog.Info($"POST request successful: {responseContent}");
                    return true;
                }
                else
                {
                    PluginLog.Warning($"POST request failed with status {response.StatusCode}: {responseContent}");
                    return false;
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, $"Failed to send POST request to {url}");
                return false;
            }
        }

        // Sends a POST request to localhost with selected text and user input
        public static async Task<Boolean> SendPostRequestWithInputAsync(String url, String selectedText, String applicationName,  String userInput)
        {
            try
            {
                var payload = new
                {
                    selectedText = selectedText ?? String.Empty,
                    applicationName = applicationName ?? "Unknown",
                    input = userInput ?? String.Empty
                };

                var json = JsonSerializer.Serialize(payload);
                var content = new StringContent(json, Encoding.UTF8, "application/json");

                var response = await _httpClient.PostAsync(url, content);
                var responseContent = await response.Content.ReadAsStringAsync();

                if (response.IsSuccessStatusCode)
                {
                    PluginLog.Info($"POST request successful: {responseContent}");
                    return true;
                }
                else
                {
                    PluginLog.Warning($"POST request failed with status {response.StatusCode}: {responseContent}");
                    return false;
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, $"Failed to send POST request to {url}");
                return false;
            }
        }

        // Sends a GET request and returns the response as a string
        public static async Task<String> SendGetRequestAsync(String url)
        {
            try
            {
                var response = await _httpClient.GetAsync(url);
                var content = await response.Content.ReadAsStringAsync();
        
                if (response.IsSuccessStatusCode)
                {
                    PluginLog.Info($"GET request successful: {content}");
                    return content;
                }
                else
                {
                    PluginLog.Warning($"GET request failed with status {response.StatusCode}: {content}");
                    return null;
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, $"Failed to send GET request to {url}");
                return null;
            }
        }

        // Disposes the HTTP client (call this in plugin Unload)
        public static void Dispose()
        {
            _httpClient?.Dispose();
        }
    }
}


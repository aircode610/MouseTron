namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Diagnostics;
    using System.IO;
    using System.Net;
    using System.Net.Sockets;
    using System.Runtime.InteropServices;
    using System.Text;
    using System.Threading;

    // Service that manages the server.py process
    public class ServerManagementService
    {
        private readonly Plugin _plugin;
        private Process _serverProcess;
        private Int32? _serverPort;
        private static readonly Object _lockObject = new Object();

        public ServerManagementService(Plugin plugin)
        {
            this._plugin = plugin ?? throw new ArgumentNullException(nameof(plugin));
        }

        // Gets the current server port (null if server is not running)
        public Int32? ServerPort => this._serverPort;

        // Starts the server.py process
        public Boolean Start()
        {
            lock (_lockObject)
            {
                if (this._serverProcess != null && !this._serverProcess.HasExited)
                {
                    PluginLog.Info("Server is already running");
                    return true;
                }

                try
                {
                    // Get parent directory (one level up from MouseTronPlugin directory)
                    PluginLog.Info("Step 1: Determining paths...");
                    
                    // Try multiple methods to get assembly location
                    String assemblyLocation = null;
                    
                    // Method 1: Try plugin.Assembly.Location
                    if (!String.IsNullOrEmpty(this._plugin.Assembly.Location))
                    {
                        assemblyLocation = this._plugin.Assembly.Location;
                        PluginLog.Info($"Got assembly location from plugin.Assembly.Location: {assemblyLocation}");
                    }
                    // Method 2: Try GetExecutingAssembly
                    else
                    {
                        try
                        {
                            var executingAssembly = System.Reflection.Assembly.GetExecutingAssembly();
                            assemblyLocation = executingAssembly.Location;
                            if (!String.IsNullOrEmpty(assemblyLocation))
                            {
                                PluginLog.Info($"Got assembly location from GetExecutingAssembly: {assemblyLocation}");
                            }
                        }
                        catch (Exception ex)
                        {
                            PluginLog.Warning($"GetExecutingAssembly failed: {ex.Message}");
                        }
                    }
                    
                    // Method 3: Try using the plugin link file (created during build)
                    if (String.IsNullOrEmpty(assemblyLocation))
                    {
                        try
                        {
                            var pluginLinkPath = RuntimeInformation.IsOSPlatform(OSPlatform.Windows)
                                ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Logi", "LogiPluginService", "Plugins", "MouseTronPlugin.link")
                                : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "Library", "Application Support", "Logi", "LogiPluginService", "Plugins", "MouseTronPlugin.link");
                            
                            if (File.Exists(pluginLinkPath))
                            {
                                var linkContent = File.ReadAllText(pluginLinkPath).Trim();
                                if (Directory.Exists(linkContent))
                                {
                                    // The link points to the bin/Debug directory, so the DLL is in bin/Debug/bin/
                                    var dllPath = Path.Combine(linkContent, "bin", "MouseTronPlugin.dll");
                                    if (File.Exists(dllPath))
                                    {
                                        assemblyLocation = dllPath;
                                        PluginLog.Info($"Got assembly location from plugin link file: {assemblyLocation}");
                                    }
                                }
                            }
                        }
                        catch (Exception ex)
                        {
                            PluginLog.Warning($"Reading plugin link file failed: {ex.Message}");
                        }
                    }
                    
                    if (String.IsNullOrEmpty(assemblyLocation))
                    {
                        PluginLog.Error("Cannot determine assembly location using any method");
                        return false;
                    }

                    var currentDir = Path.GetDirectoryName(assemblyLocation);
                    PluginLog.Info($"Current directory: {currentDir}");
                    var mouseTronPluginDir = currentDir;
                    
                    // Navigate up to find MouseTronPlugin directory
                    PluginLog.Info("Step 2: Navigating to find MouseTronPlugin directory...");
                    while (mouseTronPluginDir != null)
                    {
                        var dirName = Path.GetFileName(mouseTronPluginDir);
                        PluginLog.Info($"Checking directory: {mouseTronPluginDir} (name: {dirName})");
                        if (dirName == "MouseTronPlugin")
                        {
                            PluginLog.Info($"Found MouseTronPlugin directory: {mouseTronPluginDir}");
                            break;
                        }
                        mouseTronPluginDir = Directory.GetParent(mouseTronPluginDir)?.FullName;
                    }

                    // Now go one level up to get the parent directory (MouseTron)
                    PluginLog.Info("Step 3: Getting parent directory...");
                    var parentDirectory = mouseTronPluginDir != null 
                        ? Directory.GetParent(mouseTronPluginDir)?.FullName 
                        : null;
                    
                    if (String.IsNullOrEmpty(parentDirectory))
                    {
                        PluginLog.Error($"Cannot determine parent directory. Assembly location: {assemblyLocation}, MouseTronPlugin dir: {mouseTronPluginDir}");
                        return false;
                    }
                    PluginLog.Info($"Parent directory: {parentDirectory}");

                    PluginLog.Info("Step 4: Checking for server.py...");
                    var serverPath = Path.Combine(parentDirectory, "server.py");
                    PluginLog.Info($"Server path: {serverPath}");
                    if (!File.Exists(serverPath))
                    {
                        PluginLog.Error($"server.py not found at: {serverPath}");
                        return false;
                    }
                    PluginLog.Info("server.py found");

                    // Find a free port
                    var freePort = this.FindFreePort();
                    if (freePort == null)
                    {
                        PluginLog.Error("Could not find a free port");
                        return false;
                    }

                    this._serverPort = freePort.Value;
                    PluginLog.Info($"Found free port: {freePort.Value}");
                    PluginLog.Info($"Starting server.py on port {freePort.Value} from {serverPath}");

                    // Determine Python executable (check virtual environment first)
                    var pythonExecutable = this.GetPythonExecutable(parentDirectory);
                    if (String.IsNullOrEmpty(pythonExecutable))
                    {
                        PluginLog.Error("Python executable not found. Please ensure Python 3 is installed and in PATH.");
                        return false;
                    }
                    
                    PluginLog.Info($"Using Python executable: {pythonExecutable}");

                    // Start the server process
                    var startInfo = new ProcessStartInfo
                    {
                        FileName = pythonExecutable,
                        Arguments = $"\"{serverPath}\" -p {freePort.Value}",
                        WorkingDirectory = parentDirectory,
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true
                    };

                    this._serverProcess = new Process
                    {
                        StartInfo = startInfo,
                        EnableRaisingEvents = true
                    };

                    // Capture output and error
                    var outputBuilder = new StringBuilder();
                    var errorBuilder = new StringBuilder();
                    var outputLock = new Object();

                    this._serverProcess.OutputDataReceived += (sender, e) =>
                    {
                        if (!String.IsNullOrEmpty(e.Data))
                        {
                            lock (outputLock)
                            {
                                outputBuilder.AppendLine(e.Data);
                            }
                            PluginLog.Info($"Server output: {e.Data}");
                        }
                    };

                    this._serverProcess.ErrorDataReceived += (sender, e) =>
                    {
                        if (!String.IsNullOrEmpty(e.Data))
                        {
                            lock (outputLock)
                            {
                                errorBuilder.AppendLine(e.Data);
                            }
                            PluginLog.Warning($"Server error: {e.Data}");
                        }
                    };

                    // Handle process exit
                    this._serverProcess.Exited += (sender, e) =>
                    {
                        PluginLog.Warning($"Server process exited with code {this._serverProcess.ExitCode}");
                        lock (_lockObject)
                        {
                            this._serverPort = null;
                            this._serverProcess = null;
                        }
                    };

                    // Start the process
                    try
                    {
                        PluginLog.Info($"Executing: {pythonExecutable} \"{serverPath}\" -p {freePort.Value}");
                        PluginLog.Info($"Working directory: {parentDirectory}");
                        this._serverProcess.Start();
                        this._serverProcess.BeginOutputReadLine();
                        this._serverProcess.BeginErrorReadLine();
                        PluginLog.Info("Server process started, waiting for initialization...");
                    }
                    catch (Exception startEx)
                    {
                        PluginLog.Error(startEx, $"Exception while starting process: {startEx.Message}");
                        PluginLog.Error($"Process start info - FileName: {startInfo.FileName}, Arguments: {startInfo.Arguments}");
                        this._serverProcess = null;
                        this._serverPort = null;
                        return false;
                    }

                    // Wait a bit for the server to start and capture any errors
                    Thread.Sleep(1500);

                    // Check if process exited
                    if (this._serverProcess.HasExited)
                    {
                        var exitCode = this._serverProcess.ExitCode;
                        PluginLog.Error($"Server process exited immediately with code {exitCode}");
                        
                        // Read any remaining output/error
                        Thread.Sleep(200); // Give a bit more time for async reads
                        
                        String errorOutput;
                        String standardOutput;
                        lock (outputLock)
                        {
                            errorOutput = errorBuilder.ToString();
                            standardOutput = outputBuilder.ToString();
                        }
                        
                        if (!String.IsNullOrEmpty(errorOutput))
                        {
                            PluginLog.Error($"Server error output: {errorOutput}");
                        }
                        if (!String.IsNullOrEmpty(standardOutput))
                        {
                            PluginLog.Info($"Server standard output: {standardOutput}");
                        }
                        
                        this._serverProcess = null;
                        this._serverPort = null;
                        return false;
                    }

                    PluginLog.Info($"Server started successfully on port {this._serverPort.Value}");
                    return true;
                }
                catch (Exception ex)
                {
                    PluginLog.Error(ex, $"Failed to start server: {ex.Message}");
                    PluginLog.Error($"Exception type: {ex.GetType().Name}");
                    PluginLog.Error($"Stack trace: {ex.StackTrace}");
                    this._serverProcess = null;
                    this._serverPort = null;
                    return false;
                }
            }
        }

        // Stops the server process
        public void Stop()
        {
            lock (_lockObject)
            {
                if (this._serverProcess != null && !this._serverProcess.HasExited)
                {
                    try
                    {
                        PluginLog.Info("Stopping server process");
                        this._serverProcess.Kill();
                        this._serverProcess.WaitForExit(5000);
                        
                        if (!this._serverProcess.HasExited)
                        {
                            PluginLog.Warning("Server process did not exit within timeout, forcing kill");
                            this._serverProcess.Kill();
                        }
                        
                        this._serverProcess.Dispose();
                        PluginLog.Info("Server process stopped");
                    }
                    catch (Exception ex)
                    {
                        PluginLog.Error(ex, "Error stopping server process");
                    }
                    finally
                    {
                        this._serverProcess = null;
                        this._serverPort = null;
                    }
                }
            }
        }

        // Finds a free port on the system
        private Int32? FindFreePort()
        {
            try
            {
                var listener = new TcpListener(IPAddress.Loopback, 0);
                listener.Start();
                var port = ((IPEndPoint)listener.LocalEndpoint).Port;
                listener.Stop();
                return port;
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, "Failed to find free port");
                return null;
            }
        }

        // Gets the Python executable path
        private String GetPythonExecutable(String parentDirectory)
        {
            try
            {
                // First, try to find Python in the parent directory's virtual environment
                if (!String.IsNullOrEmpty(parentDirectory))
                {
                    // Check for common virtual environment paths (try both python3 and python)
                    var venvDirs = new[] { ".venv", "venv", "env" };
                    var pythonNames = new[] { "python3", "python" };
                    
                    PluginLog.Info($"Checking for virtual environment in: {parentDirectory}");
                    foreach (var venvDir in venvDirs)
                    {
                        foreach (var pythonName in pythonNames)
                        {
                            var venvPath = Path.Combine(parentDirectory, venvDir, "bin", pythonName);
                            PluginLog.Info($"Checking: {venvPath} (exists: {File.Exists(venvPath)})");
                            if (File.Exists(venvPath))
                            {
                                PluginLog.Info($"Found Python in virtual environment: {venvPath}");
                                return venvPath;
                            }
                        }
                    }
                    
                    PluginLog.Info($"No virtual environment found in {parentDirectory}");
                }
                
                // Fallback to system Python
                PluginLog.Info("Falling back to system Python");
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    var python = this.FindExecutable("python");
                    if (!String.IsNullOrEmpty(python)) return python;
                    return this.FindExecutable("python3");
                }
                else
                {
                    var python3 = this.FindExecutable("python3");
                    if (!String.IsNullOrEmpty(python3)) return python3;
                    return this.FindExecutable("python");
                }
            }
            catch (Exception ex)
            {
                PluginLog.Error(ex, "Failed to find Python executable");
                return null;
            }
        }

        // Finds an executable in PATH
        private String FindExecutable(String name)
        {
            try
            {
                var pathEnv = Environment.GetEnvironmentVariable("PATH");
                if (!String.IsNullOrEmpty(pathEnv))
                {
                    var paths = pathEnv.Split(Path.PathSeparator);
                    var extensions = RuntimeInformation.IsOSPlatform(OSPlatform.Windows) 
                        ? new[] { ".exe", ".bat", ".cmd", "" } 
                        : new[] { "" };

                    foreach (var path in paths)
                    {
                        foreach (var ext in extensions)
                        {
                            var fullPath = Path.Combine(path, name + ext);
                            if (File.Exists(fullPath))
                            {
                                return fullPath;
                            }
                        }
                    }
                }

                // Also try direct execution
                var process = new Process
                {
                    StartInfo = new ProcessStartInfo
                    {
                        FileName = name,
                        Arguments = "--version",
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true
                    }
                };

                try
                {
                    process.Start();
                    process.WaitForExit(1000);
                    if (process.ExitCode == 0 || !process.HasExited)
                    {
                        if (!process.HasExited)
                        {
                            process.Kill();
                        }
                        return name;
                    }
                }
                catch
                {
                    // Ignore
                }
                finally
                {
                    process?.Dispose();
                }

                return null;
            }
            catch
            {
                return null;
            }
        }
    }
}

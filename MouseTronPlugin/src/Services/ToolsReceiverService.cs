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

    // Service that manages the tools_receiver.py process
    public class ToolsReceiverService
    {
        private readonly Plugin _plugin;
        private Process _receiverProcess;
        private Int32? _receiverPort;
        private static readonly Object _lockObject = new Object();

        public ToolsReceiverService(Plugin plugin)
        {
            this._plugin = plugin ?? throw new ArgumentNullException(nameof(plugin));
        }

        // Gets the current receiver port (null if receiver is not running)
        public Int32? ReceiverPort => this._receiverPort;

        // Starts the tools_receiver.py process
        public Boolean Start()
        {
            lock (_lockObject)
            {
                if (this._receiverProcess != null && !this._receiverProcess.HasExited)
                {
                    PluginLog.Info("Tools receiver is already running");
                    return true;
                }

                try
                {
                    // Get parent directory (one level up from MouseTronPlugin directory)
                    PluginLog.Info("Step 1: Determining paths for tools receiver...");
                    
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

                    PluginLog.Info("Step 4: Checking for services/tools_receiver.py...");
                    var receiverPath = Path.Combine(parentDirectory, "services", "tools_receiver.py");
                    PluginLog.Info($"Tools receiver path: {receiverPath}");
                    if (!File.Exists(receiverPath))
                    {
                        PluginLog.Error($"tools_receiver.py not found at: {receiverPath}");
                        return false;
                    }
                    PluginLog.Info("tools_receiver.py found");

                    // Find a free port (use 8081 as default, but find free if taken)
                    var freePort = this.FindFreePort(8081);
                    if (freePort == null)
                    {
                        PluginLog.Error("Could not find a free port for tools receiver");
                        return false;
                    }

                    this._receiverPort = freePort.Value;
                    PluginLog.Info($"Found free port for tools receiver: {freePort.Value}");
                    PluginLog.Info($"Starting tools_receiver.py on port {freePort.Value} from {receiverPath}");

                    // Determine Python executable (check virtual environment first)
                    var pythonExecutable = this.GetPythonExecutable(parentDirectory);
                    if (String.IsNullOrEmpty(pythonExecutable))
                    {
                        PluginLog.Error("Python executable not found. Please ensure Python 3 is installed and in PATH.");
                        return false;
                    }
                    
                    PluginLog.Info($"Using Python executable: {pythonExecutable}");

                    // Start the receiver process
                    var startInfo = new ProcessStartInfo
                    {
                        FileName = pythonExecutable,
                        Arguments = $"\"{receiverPath}\" -p {freePort.Value}",
                        WorkingDirectory = parentDirectory,
                        UseShellExecute = false,
                        RedirectStandardOutput = true,
                        RedirectStandardError = true,
                        CreateNoWindow = true
                    };

                    this._receiverProcess = new Process
                    {
                        StartInfo = startInfo,
                        EnableRaisingEvents = true
                    };

                    // Capture output and error
                    var outputBuilder = new StringBuilder();
                    var errorBuilder = new StringBuilder();
                    var outputLock = new Object();

                    this._receiverProcess.OutputDataReceived += (sender, e) =>
                    {
                        if (!String.IsNullOrEmpty(e.Data))
                        {
                            lock (outputLock)
                            {
                                outputBuilder.AppendLine(e.Data);
                            }
                            PluginLog.Info($"Tools receiver output: {e.Data}");
                        }
                    };

                    this._receiverProcess.ErrorDataReceived += (sender, e) =>
                    {
                        if (!String.IsNullOrEmpty(e.Data))
                        {
                            lock (outputLock)
                            {
                                errorBuilder.AppendLine(e.Data);
                            }
                            PluginLog.Warning($"Tools receiver error: {e.Data}");
                        }
                    };

                    // Handle process exit
                    this._receiverProcess.Exited += (sender, e) =>
                    {
                        PluginLog.Warning($"Tools receiver process exited with code {this._receiverProcess.ExitCode}");
                        lock (_lockObject)
                        {
                            this._receiverPort = null;
                            this._receiverProcess = null;
                        }
                    };

                    // Start the process
                    try
                    {
                        PluginLog.Info($"Executing: {pythonExecutable} \"{receiverPath}\" -p {freePort.Value}");
                        PluginLog.Info($"Working directory: {parentDirectory}");
                        this._receiverProcess.Start();
                        this._receiverProcess.BeginOutputReadLine();
                        this._receiverProcess.BeginErrorReadLine();
                        PluginLog.Info("Tools receiver process started, waiting for initialization...");
                    }
                    catch (Exception startEx)
                    {
                        PluginLog.Error(startEx, $"Exception while starting tools receiver process: {startEx.Message}");
                        PluginLog.Error($"Process start info - FileName: {startInfo.FileName}, Arguments: {startInfo.Arguments}");
                        this._receiverProcess = null;
                        this._receiverPort = null;
                        return false;
                    }

                    // Wait a bit for the receiver to start and capture any errors
                    Thread.Sleep(1500);

                    // Check if process exited
                    if (this._receiverProcess.HasExited)
                    {
                        var exitCode = this._receiverProcess.ExitCode;
                        PluginLog.Error($"Tools receiver process exited immediately with code {exitCode}");
                        
                        // Read any remaining output/error
                        Thread.Sleep(200);
                        
                        String errorOutput;
                        String standardOutput;
                        lock (outputLock)
                        {
                            errorOutput = errorBuilder.ToString();
                            standardOutput = outputBuilder.ToString();
                        }
                        
                        if (!String.IsNullOrEmpty(errorOutput))
                        {
                            PluginLog.Error($"Tools receiver error output: {errorOutput}");
                        }
                        if (!String.IsNullOrEmpty(standardOutput))
                        {
                            PluginLog.Info($"Tools receiver standard output: {standardOutput}");
                        }
                        
                        this._receiverProcess = null;
                        this._receiverPort = null;
                        return false;
                    }

                    PluginLog.Info($"Tools receiver started successfully on port {this._receiverPort.Value}");
                    return true;
                }
                catch (Exception ex)
                {
                    PluginLog.Error(ex, $"Failed to start tools receiver: {ex.Message}");
                    PluginLog.Error($"Exception type: {ex.GetType().Name}");
                    PluginLog.Error($"Stack trace: {ex.StackTrace}");
                    this._receiverProcess = null;
                    this._receiverPort = null;
                    return false;
                }
            }
        }

        // Stops the receiver process
        public void Stop()
        {
            lock (_lockObject)
            {
                if (this._receiverProcess != null && !this._receiverProcess.HasExited)
                {
                    try
                    {
                        PluginLog.Info("Stopping tools receiver process");
                        this._receiverProcess.Kill();
                        this._receiverProcess.WaitForExit(5000);
                        
                        if (!this._receiverProcess.HasExited)
                        {
                            PluginLog.Warning("Tools receiver process did not exit within timeout, forcing kill");
                            this._receiverProcess.Kill();
                        }
                        
                        this._receiverProcess.Dispose();
                        PluginLog.Info("Tools receiver process stopped");
                    }
                    catch (Exception ex)
                    {
                        PluginLog.Error(ex, "Error stopping tools receiver process");
                    }
                    finally
                    {
                        this._receiverProcess = null;
                        this._receiverPort = null;
                    }
                }
            }
        }

        // Finds a free port on the system, optionally starting from a preferred port
        private Int32? FindFreePort(Int32 preferredPort = 0)
        {
            try
            {
                // If preferred port is specified, try it first
                if (preferredPort > 0)
                {
                    try
                    {
                        var testListener = new TcpListener(IPAddress.Loopback, preferredPort);
                        testListener.Start();
                        testListener.Stop();
                        return preferredPort;
                    }
                    catch
                    {
                        // Port is in use, fall through to find any free port
                    }
                }
                
                // Find any free port
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


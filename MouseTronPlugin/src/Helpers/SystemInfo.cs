namespace Loupedeck.MouseTronPlugin
{
    using System;
    using System.Diagnostics;
    using System.IO;
    using System.Runtime.InteropServices;
    using System.Text;
    using System.Threading;

    // Helper class for getting system information like selected text and current application name
    internal static class SystemInfo
    {
        // Gets the current clipboard text
        public static String GetClipboardText()
        {
            try
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    // Windows: Use PowerShell to get clipboard
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "powershell",
                            Arguments = "-NoProfile -Command \"Get-Clipboard\"",
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var text = process.StandardOutput.ReadToEnd();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0 && !String.IsNullOrEmpty(error))
                    {
                        PluginLog.Warning($"Get-Clipboard error: {error}");
                    }
                    
                    return text.Trim();
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                {
                    // macOS: Use pbpaste
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/pbpaste",
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var text = process.StandardOutput.ReadToEnd();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0 && !String.IsNullOrEmpty(error))
                    {
                        PluginLog.Warning($"pbpaste error: {error}");
                    }
                    
                    return text.Trim();
                }
                else
                {
                    // Linux: Use xclip
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/xclip",
                            Arguments = "-selection clipboard -o",
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var text = process.StandardOutput.ReadToEnd();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0 && !String.IsNullOrEmpty(error))
                    {
                        PluginLog.Warning($"xclip error: {error}");
                    }
                    
                    return text.Trim();
                }
            }
            catch (Exception ex)
            {
                PluginLog.Warning(ex, "Failed to get clipboard text");
                return String.Empty;
            }
        }

        // Sets clipboard text
        public static Boolean SetClipboardText(String text)
        {
            if (String.IsNullOrEmpty(text))
            {
                PluginLog.Warning("SetClipboardText called with empty text");
                return false;
            }

            PluginLog.Info($"SetClipboardText called with text length: {text.Length}");

            try
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    // Windows: Use PowerShell Set-Clipboard
                    // Write text to a temp file first to avoid escaping issues
                    var tempFile = System.IO.Path.GetTempFileName();
                    System.IO.File.WriteAllText(tempFile, text, Encoding.UTF8);
                    
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "powershell",
                            Arguments = $"-NoProfile -Command \"Get-Content '{tempFile}' -Raw | Set-Clipboard\"",
                            UseShellExecute = false,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    // Clean up temp file
                    try { System.IO.File.Delete(tempFile); } catch { }
                    
                    if (process.ExitCode != 0)
                    {
                        PluginLog.Warning($"Set-Clipboard failed: {error}");
                        return false;
                    }
                    
                    // Verify
                    Thread.Sleep(100);
                    var verify = GetClipboardText();
                    return verify == text;
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                {
                    // macOS: Try multiple methods for maximum reliability
                    
                    // Method 2: Use pbcopy with stdin (fallback)
                    try
                    {
                        var pbcopyProcess = new Process
                        {
                            StartInfo = new ProcessStartInfo
                            {
                                FileName = "/usr/bin/pbcopy",
                                UseShellExecute = false,
                                RedirectStandardInput = true,
                                RedirectStandardError = true,
                                CreateNoWindow = true
                            }
                        };
                        pbcopyProcess.Start();
                        
                        // Write using StreamWriter for proper encoding
                        using (var writer = new StreamWriter(pbcopyProcess.StandardInput.BaseStream, Encoding.UTF8, leaveOpen: false))
                        {
                            writer.Write(text);
                            writer.Flush();
                        }
                        
                        var pbcopyError = pbcopyProcess.StandardError.ReadToEnd();
                        pbcopyProcess.WaitForExit();
                        
                        if (pbcopyProcess.ExitCode == 0)
                        {
                            Thread.Sleep(150);
                            var verify = GetClipboardText();
                            if (verify == text)
                            {
                                PluginLog.Info($"Clipboard set successfully via pbcopy (length: {text.Length})");
                                return true;
                            }
                            else
                            {
                                PluginLog.Warning($"pbcopy succeeded but verification failed. Expected: {text.Length}, Got: {verify?.Length ?? 0}");
                            }
                        }
                        else
                        {
                            PluginLog.Warning($"pbcopy failed (exit {pbcopyProcess.ExitCode}): {pbcopyError}");
                        }
                    }
                    catch (Exception pbcopyEx)
                    {
                        PluginLog.Warning(pbcopyEx, "pbcopy method failed");
                    }
                    
                    // Method 1: Use osascript (most reliable for setting clipboard)
                    try
                    {
                        // Escape for AppleScript: backslash and quotes
                        var escapedText = text.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
                        var script = $"set the clipboard to \"{escapedText}\"";
                        
                        var osaProcess = new Process
                        {
                            StartInfo = new ProcessStartInfo
                            {
                                FileName = "/usr/bin/osascript",
                                Arguments = $"-e '{script}'",
                                UseShellExecute = false,
                                RedirectStandardError = true,
                                CreateNoWindow = true
                            }
                        };
                        osaProcess.Start();
                        var osaError = osaProcess.StandardError.ReadToEnd();
                        osaProcess.WaitForExit();
                        
                        if (osaProcess.ExitCode == 0)
                        {
                            Thread.Sleep(150);
                            var verify = GetClipboardText();
                            if (verify == text)
                            {
                                PluginLog.Info($"Clipboard set successfully via osascript (length: {text.Length})");
                                return true;
                            }
                            else
                            {
                                PluginLog.Warning($"osascript succeeded but verification failed. Expected: {text.Length}, Got: {verify?.Length ?? 0}");
                            }
                        }
                        else
                        {
                            PluginLog.Warning($"osascript failed (exit {osaProcess.ExitCode}): {osaError}");
                        }
                    }
                    catch (Exception osaEx)
                    {
                        PluginLog.Warning(osaEx, "osascript method failed");
                    }
                    
                    PluginLog.Error("All macOS clipboard setting methods failed");
                    return false;
                }
                else
                {
                    // Linux: Use xclip
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/xclip",
                            Arguments = "-selection clipboard",
                            UseShellExecute = false,
                            RedirectStandardInput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    
                    var bytes = Encoding.UTF8.GetBytes(text);
                    process.StandardInput.BaseStream.Write(bytes, 0, bytes.Length);
                    process.StandardInput.Flush();
                    process.StandardInput.Close();
                    
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0)
                    {
                        PluginLog.Warning($"xclip failed: {error}");
                        return false;
                    }
                    
                    // Verify
                    Thread.Sleep(100);
                    var verify = GetClipboardText();
                    return verify == text;
                }
            }
            catch (Exception ex)
            {
                PluginLog.Warning(ex, "Failed to set clipboard text");
                return false;
            }
        }

        // Copies selected text by sending copy keyboard shortcut (Cmd+C on macOS, Ctrl+C on Windows)
        // Note: SDK's SendKeyboardShortcut doesn't support modifier key combinations, so we use platform-specific methods
        public static void CopySelectedText(Plugin plugin)
        {
            try
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    // Windows: Use PowerShell SendKeys
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "powershell",
                            Arguments = "-NoProfile -Command \"Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('^c')\"",
                            UseShellExecute = false,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0)
                    {
                        PluginLog.Warning($"SendKeys Ctrl+C failed: {error}");
                    }
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                {
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/osascript",
                            Arguments = "-e \"tell application \\\"System Events\\\" to keystroke \\\"c\\\" using {command down}\"",
                            UseShellExecute = false,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };

                    process.Start();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();

                    if (process.ExitCode != 0)
                    {
                        PluginLog.Warning($"AppleScript Cmd+C failed: {error}");
                    }
                }
                else
                {
                    // Linux: Use xdotool
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/xdotool",
                            Arguments = "key ctrl+c",
                            UseShellExecute = false,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0)
                    {
                        PluginLog.Warning($"xdotool Ctrl+C failed: {error}");
                    }
                }
            }
            catch (Exception ex)
            {
                PluginLog.Warning(ex, "Failed to send copy keyboard shortcut");
            }
        }

        // Gets the name of the currently active application
        public static String GetCurrentApplicationName()
        {
            try
            {
                if (RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
                {
                    // Windows: Get foreground window process name
                    var hwnd = GetForegroundWindow();
                    if (hwnd != IntPtr.Zero)
                    {
                        GetWindowThreadProcessId(hwnd, out var processId);
                        var process = Process.GetProcessById((Int32)processId);
                        return process.ProcessName;
                    }
                }
                else if (RuntimeInformation.IsOSPlatform(OSPlatform.OSX))
                {
                    // macOS: Use AppleScript to get frontmost application
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/osascript",
                            Arguments = "-e \"tell application \\\"System Events\\\" to get name of first application process whose frontmost is true\"",
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var appName = process.StandardOutput.ReadToEnd();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0 && !String.IsNullOrEmpty(error))
                    {
                        PluginLog.Warning($"Get app name error: {error}");
                    }
                    
                    return appName.Trim();
                }
                else
                {
                    // Linux: Use xdotool to get active window
                    var process = new Process
                    {
                        StartInfo = new ProcessStartInfo
                        {
                            FileName = "/usr/bin/xdotool",
                            Arguments = "getactivewindow getwindowname",
                            UseShellExecute = false,
                            RedirectStandardOutput = true,
                            RedirectStandardError = true,
                            CreateNoWindow = true
                        }
                    };
                    process.Start();
                    var windowName = process.StandardOutput.ReadToEnd();
                    var error = process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    
                    if (process.ExitCode != 0 && !String.IsNullOrEmpty(error))
                    {
                        PluginLog.Warning($"xdotool get window error: {error}");
                    }
                    
                    return windowName.Trim();
                }
            }
            catch (Exception ex)
            {
                PluginLog.Warning(ex, "Failed to get current application name");
                return "Unknown";
            }
            return String.Empty;
        }

        // Windows API declarations for getting foreground window
        [DllImport("user32.dll")]
        private static extern IntPtr GetForegroundWindow();

        [DllImport("user32.dll", SetLastError = true)]
        private static extern UInt32 GetWindowThreadProcessId(IntPtr hWnd, out UInt32 lpdwProcessId);
    }
}


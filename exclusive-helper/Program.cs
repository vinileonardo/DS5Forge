using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Principal;
using System.Text.Json;
using HIDMaestro;

namespace DS5Forge.ExclusiveHelper;

internal static class Program
{
    private const int ProtocolVersion = 1;
    private const string ProfileId = "dualsense";
    private const string IdentityKey = "ds5forge:exclusive:dualsense";

    public static int Main(string[] args)
    {
        try
        {
            if (HasFlag(args, "--probe"))
                return Probe();
            if (HasFlag(args, "--install-driver"))
                return InstallDriver();

            int requestedProtocol = IntArg(args, "--protocol-version") ?? 0;
            int parentPid = IntArg(args, "--parent-pid") ?? 0;
            if (requestedProtocol != ProtocolVersion)
                return Fatal($"unsupported protocol version {requestedProtocol}");
            if (parentPid <= 0 || !ValidateParent(parentPid))
                return Fatal("DS5Forge parent process could not be verified");

            using var session = new ExclusiveSession(parentPid);
            session.StartParentWatchdog();

            string? line;
            while ((line = Console.ReadLine()) is not null)
            {
                if (string.IsNullOrWhiteSpace(line))
                    continue;
                try
                {
                    using JsonDocument document = JsonDocument.Parse(line);
                    var response = session.Handle(document.RootElement);
                    Console.Out.WriteLine(JsonSerializer.Serialize(response));
                    Console.Out.Flush();
                }
                catch (Exception ex)
                {
                    WriteResponse(new { ok = false, error = SafeMessage(ex) });
                }
            }
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(SafeMessage(ex));
            return 1;
        }
    }

    private static int Probe()
    {
        using var context = new HMContext();
        context.LoadDefaultProfiles();
        WriteResponse(new
        {
            ok = true,
            protocol_version = ProtocolVersion,
            provider = "HIDMaestro",
            profile = ProfileId,
            driver_installed = context.IsDriverInstalled,
            elevated = IsElevated(),
        });
        return 0;
    }

    private static int InstallDriver()
    {
        if (!IsElevated())
            return Fatal("HIDMaestro driver installation requires an elevated Administrator process");
        using var context = new HMContext();
        context.LoadDefaultProfiles();
        context.InstallDriver();
        WriteResponse(new { ok = true, driver_installed = context.IsDriverInstalled });
        return context.IsDriverInstalled ? 0 : 2;
    }

    private static bool ValidateParent(int pid)
    {
        try
        {
            using Process parent = Process.GetProcessById(pid);
            if (parent.HasExited)
                return false;
            string name = parent.ProcessName;
            return name.Equals("ds5forge-core", StringComparison.OrdinalIgnoreCase)
                || name.Equals("DS5ForgeCore", StringComparison.OrdinalIgnoreCase)
                || name.Equals("python", StringComparison.OrdinalIgnoreCase)
                || name.Equals("python3", StringComparison.OrdinalIgnoreCase);
        }
        catch
        {
            return false;
        }
    }

    private static bool IsElevated()
    {
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        var principal = new WindowsPrincipal(identity);
        return principal.IsInRole(WindowsBuiltInRole.Administrator);
    }

    private static int Fatal(string message)
    {
        WriteResponse(new { ok = false, error = message });
        return 2;
    }

    private static void WriteResponse(object response)
    {
        Console.Out.WriteLine(JsonSerializer.Serialize(response));
        Console.Out.Flush();
    }

    private static bool HasFlag(string[] args, string name) =>
        args.Any(arg => string.Equals(arg, name, StringComparison.OrdinalIgnoreCase));

    private static int? IntArg(string[] args, string name)
    {
        for (int index = 0; index + 1 < args.Length; index++)
        {
            if (string.Equals(args[index], name, StringComparison.OrdinalIgnoreCase)
                && int.TryParse(args[index + 1], out int value))
                return value;
        }
        return null;
    }

    private static string SafeMessage(Exception exception)
    {
        string message = exception.Message?.Trim() ?? exception.GetType().Name;
        return message.Length <= 500 ? message : message[..500];
    }
}

internal sealed class ExclusiveSession : IDisposable
{
    private readonly object _gate = new();
    private readonly int _parentPid;
    private readonly ConcurrentQueue<byte[]> _outputReports = new();
    private HMContext? _context;
    private HMController? _controller;
    private HMProfile? _profile;
    private string? _token;
    private int _generation;
    private bool _disposed;

    public ExclusiveSession(int parentPid) => _parentPid = parentPid;

    public void StartParentWatchdog()
    {
        _ = Task.Run(async () =>
        {
            while (!_disposed)
            {
                await Task.Delay(500).ConfigureAwait(false);
                try
                {
                    using Process parent = Process.GetProcessById(_parentPid);
                    if (!parent.HasExited)
                        continue;
                }
                catch
                {
                    // Parent disappeared. Fall through to fail-safe teardown.
                }
                Dispose();
                Environment.Exit(0);
            }
        });
    }

    public object Handle(JsonElement request)
    {
        string operation = RequiredString(request, "op");
        return operation switch
        {
            "acquire" => Acquire(request),
            "heartbeat" => Heartbeat(request),
            "submit_state" => SubmitState(request),
            "release" => Release(request),
            "recover_stale" => RecoverStale(),
            _ => throw new InvalidOperationException($"unsupported operation '{operation}'"),
        };
    }

    private object Acquire(JsonElement request)
    {
        string token = RequiredString(request, "token");
        int generation = RequiredInt(request, "generation");
        lock (_gate)
        {
            ThrowIfDisposed();
            if (_controller is not null)
            {
                EnsureOwner(token, generation);
                return Success();
            }
            if (!IsElevated())
                throw new UnauthorizedAccessException(
                    "Exclusive helper is not elevated. Windows validation must run DS5Forge elevated until the installed broker service is available.");

            var context = new HMContext();
            try
            {
                context.LoadDefaultProfiles();
                if (!context.IsDriverInstalled)
                    throw new InvalidOperationException(
                        "HIDMaestro driver is not installed. Run DS5ForgeExclusiveHelper.exe --install-driver from an elevated process first.");
                HMProfile profile = context.GetProfile("dualsense")
                    ?? throw new InvalidOperationException("HIDMaestro DualSense profile is unavailable");
                HMController controller = context.CreateController(profile, "ds5forge:exclusive:dualsense");
                controller.OutputReceived += OnOutputReceived;
                _context = context;
                _profile = profile;
                _controller = controller;
                _token = token;
                _generation = generation;
                return Success();
            }
            catch
            {
                context.Dispose();
                throw;
            }
        }
    }

    private object Heartbeat(JsonElement request)
    {
        lock (_gate)
        {
            EnsureActiveOwner(request);
            EnsureParentAlive();
            return Success();
        }
    }

    private object SubmitState(JsonElement request)
    {
        lock (_gate)
        {
            EnsureActiveOwner(request);
            EnsureParentAlive();
            HMController controller = _controller!;
            HMProfile profile = _profile!;
            JsonElement input = RequiredObject(request, "input");
            JsonElement battery = RequiredObject(request, "battery");
            HMGamepadState state = BuildState(profile, input, battery);
            controller.SubmitState(in state);
            return Success(DrainOutputReports());
        }
    }

    private object Release(JsonElement request)
    {
        lock (_gate)
        {
            if (_controller is null)
                return Success();
            if (request.TryGetProperty("token", out _) || request.TryGetProperty("generation", out _))
                EnsureActiveOwner(request);
            TeardownLocked();
            return Success();
        }
    }

    private object RecoverStale()
    {
        lock (_gate)
        {
            TeardownLocked();
            if (!IsElevated())
                throw new UnauthorizedAccessException("HIDMaestro stale recovery requires an elevated process");
            HMContext.RemoveAllVirtualControllers(preserveInstall: true);
            return Success();
        }
    }

    private void OnOutputReceived(HMController _, HMOutputPacket packet)
    {
        if (packet.Source != HMOutputSource.HidOutput || packet.ReportId != 0x02)
            return;
        byte[] payload = packet.Data.ToArray();
        byte[] report;
        if (payload.Length == 63)
        {
            report = new byte[64];
            report[0] = packet.ReportId;
            Buffer.BlockCopy(payload, 0, report, 1, payload.Length);
        }
        else if (payload.Length == 64 && payload[0] == packet.ReportId)
        {
            report = payload;
        }
        else
        {
            return;
        }
        _outputReports.Enqueue(report);
        while (_outputReports.Count > 64 && _outputReports.TryDequeue(out _))
        {
        }
    }

    private string[] DrainOutputReports()
    {
        var reports = new List<string>(32);
        while (reports.Count < 32 && _outputReports.TryDequeue(out byte[]? report))
            reports.Add(Convert.ToHexString(report));
        return reports.ToArray();
    }

    private static HMGamepadState BuildState(HMProfile profile, JsonElement input, JsonElement battery)
    {
        JsonElement sticks = RequiredObject(input, "sticks");
        float leftX = UnitAxis(Float(sticks, "left_x"));
        float leftY = UnitAxis(Float(sticks, "left_y"));
        float rightX = UnitAxis(Float(sticks, "right_x"));
        float rightY = UnitAxis(Float(sticks, "right_y"));
        float leftTrigger = Clamp01(Float(input, "l2"));
        float rightTrigger = Clamp01(Float(input, "r2"));

        HMButton buttons = HMButton.None;
        if (Bool(input, "cross")) buttons |= HMButton.Cross;
        if (Bool(input, "circle")) buttons |= HMButton.Circle;
        if (Bool(input, "square")) buttons |= HMButton.Square;
        if (Bool(input, "triangle")) buttons |= HMButton.Triangle;
        if (Bool(input, "l1")) buttons |= HMButton.LeftBumper;
        if (Bool(input, "r1")) buttons |= HMButton.RightBumper;
        if (Bool(input, "share")) buttons |= HMButton.Back;
        if (Bool(input, "options")) buttons |= HMButton.Start;
        if (Bool(input, "l3")) buttons |= HMButton.LeftStick;
        if (Bool(input, "r3")) buttons |= HMButton.RightStick;
        if (Bool(input, "ps")) buttons |= HMButton.Guide;
        if (Bool(input, "touchpad_button")) buttons |= HMButton.Touchpad;
        if (Bool(input, "mic_button")) buttons |= HMButton.Misc1;

        JsonElement touch0 = RequiredObject(input, "touch0");
        JsonElement touch1 = RequiredObject(input, "touch1");
        int level = Math.Clamp(Int(battery, "level"), 0, 100);
        bool charging = NullableBool(battery, "charging") ?? false;

        return new HMGamepadState
        {
            Axes = HMGamepadStateHelpers.StandardAxes(
                profile,
                leftStickX: leftX,
                leftStickY: leftY,
                rightStickX: rightX,
                rightStickY: rightY,
                leftTrigger: leftTrigger,
                rightTrigger: rightTrigger),
            Buttons = buttons,
            Hat = Hat(input),
            TouchpadFinger0Active = Bool(touch0, "active"),
            TouchpadFinger0X = ClampUShort(Float(touch0, "x"), 0, 1919),
            TouchpadFinger0Y = ClampUShort(Float(touch0, "y"), 0, 1079),
            TouchpadFinger0Id = (byte)(Math.Clamp(Int(touch0, "contact_id", 0), 0, 127)),
            TouchpadFinger1Active = Bool(touch1, "active"),
            TouchpadFinger1X = ClampUShort(Float(touch1, "x"), 0, 1919),
            TouchpadFinger1Y = ClampUShort(Float(touch1, "y"), 0, 1079),
            TouchpadFinger1Id = (byte)(Math.Clamp(Int(touch1, "contact_id", 0), 0, 127)),
            BatteryLevel = (byte)Math.Clamp((level + 5) / 10, 0, 10),
            BatteryCharging = charging,
            BatteryFull = level >= 100,
        };
    }

    private static HMHat Hat(JsonElement input)
    {
        bool up = Bool(input, "dpad_up");
        bool down = Bool(input, "dpad_down");
        bool left = Bool(input, "dpad_left");
        bool right = Bool(input, "dpad_right");
        if (up && right) return HMHat.NorthEast;
        if (down && right) return HMHat.SouthEast;
        if (down && left) return HMHat.SouthWest;
        if (up && left) return HMHat.NorthWest;
        if (up) return HMHat.North;
        if (right) return HMHat.East;
        if (down) return HMHat.South;
        if (left) return HMHat.West;
        return HMHat.None;
    }

    private object Success(string[]? outputReports = null) => new
    {
        ok = true,
        provider = "HIDMaestro",
        profile = "dualsense",
        output_reports = outputReports ?? Array.Empty<string>(),
    };

    private void EnsureActiveOwner(JsonElement request)
    {
        if (_controller is null || _token is null)
            throw new InvalidOperationException("Exclusive virtual controller is not active");
        EnsureOwner(RequiredString(request, "token"), RequiredInt(request, "generation"));
    }

    private void EnsureOwner(string token, int generation)
    {
        if (!string.Equals(_token, token, StringComparison.Ordinal) || _generation != generation)
            throw new InvalidOperationException("Exclusive ownership token or generation does not match");
    }

    private void EnsureParentAlive()
    {
        try
        {
            using Process parent = Process.GetProcessById(_parentPid);
            if (!parent.HasExited)
                return;
        }
        catch
        {
        }
        TeardownLocked();
        throw new InvalidOperationException("DS5Forge parent process exited");
    }

    private void TeardownLocked()
    {
        HMController? controller = _controller;
        HMContext? context = _context;
        _controller = null;
        _profile = null;
        _context = null;
        _token = null;
        _generation = 0;
        while (_outputReports.TryDequeue(out _))
        {
        }
        if (controller is not null)
        {
            try { controller.OutputReceived -= OnOutputReceived; } catch { }
            try { controller.Dispose(); } catch { }
        }
        try { context?.Dispose(); } catch { }
    }

    private void ThrowIfDisposed()
    {
        if (_disposed)
            throw new ObjectDisposedException(nameof(ExclusiveSession));
    }

    public void Dispose()
    {
        lock (_gate)
        {
            if (_disposed)
                return;
            _disposed = true;
            TeardownLocked();
        }
    }

    private static bool IsElevated()
    {
        using WindowsIdentity identity = WindowsIdentity.GetCurrent();
        var principal = new WindowsPrincipal(identity);
        return principal.IsInRole(WindowsBuiltInRole.Administrator);
    }

    private static string RequiredString(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.String)
            throw new InvalidOperationException($"'{name}' must be a string");
        return value.GetString() ?? throw new InvalidOperationException($"'{name}' cannot be null");
    }

    private static int RequiredInt(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || !value.TryGetInt32(out int result))
            throw new InvalidOperationException($"'{name}' must be an integer");
        return result;
    }

    private static JsonElement RequiredObject(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException($"'{name}' must be an object");
        return value;
    }

    private static bool Bool(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value)) return false;
        return value.ValueKind == JsonValueKind.True;
    }

    private static bool? NullableBool(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind == JsonValueKind.Null) return null;
        if (value.ValueKind == JsonValueKind.True) return true;
        if (value.ValueKind == JsonValueKind.False) return false;
        return null;
    }

    private static float Float(JsonElement element, string name)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || !value.TryGetSingle(out float result) || !float.IsFinite(result))
            return 0f;
        return result;
    }

    private static int Int(JsonElement element, string name, int fallback = 0)
    {
        if (!element.TryGetProperty(name, out JsonElement value) || value.ValueKind == JsonValueKind.Null || !value.TryGetInt32(out int result))
            return fallback;
        return result;
    }

    private static float UnitAxis(float value) => Clamp01((Math.Clamp(value, -1f, 1f) + 1f) * 0.5f);
    private static float Clamp01(float value) => Math.Clamp(float.IsFinite(value) ? value : 0f, 0f, 1f);
    private static ushort ClampUShort(float value, int min, int max) =>
        (ushort)Math.Clamp((int)MathF.Round(float.IsFinite(value) ? value : 0f), min, max);
}

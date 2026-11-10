using System;
using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Principal;
using System.Windows.Forms;

internal static class WindowsInstaller
{
    [STAThread]
    private static int Main(string[] args)
    {
        bool selfTest = args.Length == 1 && args[0] == "--self-test";
        try
        {
            if (selfTest)
                return TestPackage();
            if (args.Length != 0)
                return 2;

            using (WindowsIdentity identity = WindowsIdentity.GetCurrent())
            {
                if (identity.Name.EndsWith("\\Filhos", StringComparison.OrdinalIgnoreCase))
                    return 3;

                if (!new WindowsPrincipal(identity).IsInRole(WindowsBuiltInRole.Administrator))
                {
                    Process.Start(new ProcessStartInfo(Application.ExecutablePath) {
                        UseShellExecute = true, Verb = "runas"
                    });
                    return 0;
                }
            }

            string installRoot = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "FaceKids");
            Directory.CreateDirectory(installRoot);
            if ((File.GetAttributes(installRoot) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("A pasta FaceKids em Arquivos de Programas e um link.");

            // A new directory leaves any currently running installation intact.
            string release = Path.Combine(installRoot, "app-" + Guid.NewGuid().ToString("N"));
            Extract(release);
            using (Process wizard = StartPython(release, "pythonw.exe", "-E -s -m facekids.launcher --setup"))
            {
                wizard.WaitForExit();
                return wizard.ExitCode;
            }
        }
        catch (Win32Exception error)
        {
            if (error.NativeErrorCode == 1223)
                return 1223;
            return Fail(error, selfTest);
        }
        catch (Exception error)
        {
            return Fail(error, selfTest);
        }
    }

    private static int Fail(Exception error, bool selfTest)
    {
        if (!selfTest)
            MessageBox.Show(error.Message, "Instalador FaceKids", MessageBoxButtons.OK, MessageBoxIcon.Error);
        return 1;
    }

    private static Process StartPython(string directory, string executable, string arguments)
    {
        ProcessStartInfo start = new ProcessStartInfo(Path.Combine(directory, "runtime", executable), arguments) {
            WorkingDirectory = directory, UseShellExecute = false, CreateNoWindow = true
        };
        start.EnvironmentVariables["FACEKIDS_ROOT"] = directory;
        return Process.Start(start);
    }

    private static void Extract(string destination)
    {
        using (Stream payload = Assembly.GetExecutingAssembly().GetManifestResourceStream("FaceKidsPayload"))
        using (ZipArchive archive = new ZipArchive(payload, ZipArchiveMode.Read))
            archive.ExtractToDirectory(destination);
    }

    private static int TestPackage()
    {
        string temporary = Path.Combine(Path.GetTempPath(), "FaceKids-test-" + Guid.NewGuid().ToString("N"));
        try
        {
            Extract(temporary);
            using (Process test = StartPython(temporary, "python.exe", "-E -s -m facekids.package_check"))
            {
                test.WaitForExit();
                return test.ExitCode;
            }
        }
        finally
        {
            if (Directory.Exists(temporary))
                Directory.Delete(temporary, true);
        }
    }
}

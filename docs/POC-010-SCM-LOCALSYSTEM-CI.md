# P0-10 - SCM LocalSystem on disposable Windows runner

**Scope: CI only. Never run this installation workflow on the family's PC.**

The Windows SCM proof is validated on the GitHub-hosted ephemeral
windows-latest runner. This tests the actual service process context
and WinSQLite ProgramData path, not only the standalone host process.

Sequence:
1. Compile native broker with MSVC + WinSQLite.
2. Run isolated --self-test with SQLite quota/ACL and WTS checks.
3. Check that the service name and test data directory do not exist.
4. Register a demand-start service as LocalSystem with sc.exe.
5. Start it, verify SERVICE_RUNNING and SQLite database in ProgramData.
6. Run an elevated PING client, expecting PONG.
7. Run a non-SYSTEM administrator PRECHECK, expecting DENIED.
8. In finally, stop/delete service and delete the test-only directory.

This workflow cannot grant Windows logon credentials and does not
register a Credential Provider. It does not store any facial images.
The target SID is not configured: no precheck may return positive.

**Limitation:** a successful SCM install/rollback on a disposable
runner does not prove Windows LogonUI, facial liveness or camera
availability on the secure desktop. Those still require isolated VM
testing before considering any installation on the PC.

Link: .github/workflows/windows-broker-scm-vm.yml

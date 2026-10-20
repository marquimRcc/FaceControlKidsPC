# P0-16 - Negative SCM identity test

A GitHub-hosted Windows runner installs the diagnostic broker as LocalService
and verifies that it remains stopped and does not create a ProgramData quota DB.

The same runner then starts it as LocalSystem and confirms normal diagnostics.
Both temporary test service registrations are removed on completion.

This is a regression test for service misconfiguration only. It is not
facial authentication, and nothing was installed on the family's computer.

See .github/workflows/windows-broker-scm-vm.yml.

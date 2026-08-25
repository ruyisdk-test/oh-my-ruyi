# Operations And Safety

The GUI performs package-manager activation and may write raw images to host
storage. These operations are safe only when their boundary checks remain
intact. This document records the checks that a refactor must preserve.

## Trusted And Untrusted Inputs

Treat repository remotes, local metadata trees, strategy plugins, and custom
release URLs as trusted application inputs. Custom release URLs currently use
HTTPS validation but do not have signature or checksum verification; do not
describe them as verified artifacts.

Treat all storage paths selected by the user as untrusted. A path string is not
an identity. The selected device fingerprint must be recorded at review and
checked immediately before flashing and again at every actual `dd` invocation.

## Storage Flow

```text
discover -> display mounted state -> user selects path
         -> record fingerprint at review
         -> revalidate path/fingerprint/mount before flash
         -> revalidate again inside FlashWorker before each dd spawn
```

`host_storage.py` owns platform-specific discovery. Linux uses `/sys/block`,
`/dev`, and ruyi's mount parser; holder relationships are followed for
device-mapper, LUKS, LVM, RAID, and other stacked devices. macOS uses
`diskutil` plist data and raw whole-disk paths. Discovery failure fails closed;
a file chooser does not prove that a target is safe.

Mounted disks and partitions require explicit confirmation. A confirmation is
only a user intent record; it never replaces the immediate revalidation at the
destructive boundary.

## Flash Interception

`FlashWorker` temporarily intercepts ruyi's plugin host callbacks so prompts and
subprocess output can be shown in Qt. It must restore the original callbacks in
a `finally` block. For a `dd` command it requires exactly one explicit `of=`
target, maps that path to a reviewed partition, compares fingerprints, and
checks mount state. No strategy-specific board command is hard-coded in the
GUI.

Cancellation sets an event, signals the process group, drains output where
possible, escalates to `SIGKILL` after the grace period, and emits the cancelled
result only after process cleanup. Do not replace process-group termination
with a UI flag.

## Version Activation

Version binaries live under the managed versions directory. The active version
is derived from the managed activation link; do not add a second state file.
Activation may use a privileged helper when the link directory is not writable.
Only managed binaries and the managed link may be changed.

If the activation path contains an unmanaged file or symlink, ask for explicit
confirmation and preserve it as a numbered `.bak` before replacing it. The
first-use flow must use the same worker, helper, backup, cancellation, and
cleanup path as the Version Management tab.

## First-Use Eligibility

The setup is offered only when all of these are true:

1. ruyi telemetry installation state is absent;
2. no external `ruyi` resolves on PATH after excluding the directory beside the
   running Python executable;
3. the managed Oh My Ruyi data root is absent.

This is a filesystem/PATH predicate, not a completion marker. A failed or
cancelled initial download must remove empty managed directories so the next
launch can offer setup again. The dialog renders steps; the main window starts
the normal release catalog, version download, activation, repository update,
and About transition.

## Repository Mutations

`repo_manager.py` may parse TOML to preserve order and validate display state,
but every mutation uses ruyi's `ConfigEditor`. The built-in `ruyisdk` entry is
first and cannot be removed. Repository update/news operations run in child
processes and are cancellable as process groups.

## Localization And Output

Use `locale_environment()` for standard subprocesses and
`apply_qprocess_locale()` for QProcess. Route Rich renderables, links, ANSI
styles, progress, and carriage-return updates through `QtRuyiLogger` and
`RichTextView`. Operation targets prevent delayed output from leaking into a
different view.

## Refactor Safety Rules

- Do not move a safety check into a widget-only helper.
- Do not catch `BaseException` and continue after a destructive boundary fails.
- Do not reuse a stale prepared plan after changing device, variant, image,
  package versions, repository, or storage target.
- Do not test privileged or destructive operations against real system paths.
- Keep compatibility wrappers behaviorless; they must not bypass validation.

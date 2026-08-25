# Operations and Safety

This document describes operation order, trust boundaries, destructive-command
checks, cancellation behavior, and failure recovery. It is the detailed
reference for changes to repositories, downloads, activation, first-use,
storage, flashing, sudo helpers, and child processes.

The core rule is fail closed: a missing fingerprint, unknown topology, stale
process identity, or failed boundary check must stop the operation rather than
guessing what the user intended.

## Trust Boundaries

The application treats these inputs as trusted but reviewable:

- ruyi release catalog URLs and custom release URLs;
- repository remotes and local metadata trees;
- ruyi metadata entities and strategy/plugin code;
- package atoms and generated flash arguments;
- paths selected in the Storage page.

Custom release URLs must use HTTPS. The application currently does not verify
release signatures or checksums, and downloaded binaries are executable. A
trusted HTTPS source is therefore still required. Repository remotes and local
metadata can also determine package contents and flashing commands; use the
Review page to inspect commands before flashing.

The GUI does not treat a path string as proof of device identity. Device
fingerprints, mount topology, and the destructive command boundary provide the
actual storage safety checks.

## First-Use Offer

`should_offer_first_use_setup()` offers setup only if all conditions hold:

1. ruyi telemetry `installation.json` is absent;
2. no executable named `ruyi` outside the current Python environment resolves
   on `PATH`;
3. the Oh My Ruyi managed data directory is absent.

The PATH search excludes only the directory containing `sys.executable`; later
PATH entries are still searched for an external installation. Managed data
paths use ruyi's XDG helper, including macOS Application Support defaults.

There is no completion marker. A failed or cancelled first download must not
leave an empty managed data root, because its existence would suppress the
offer on the next launch.

## Release Catalog and Downloads

The release catalog uses a primary HTTPS endpoint and a fixed HTTPS fallback.
The UI filters candidates by platform and architecture, and first-use prefers
the newest compatible stable release before falling back to another channel.

Custom URL flow:

1. The user enters a URL in Version Management.
2. `release_from_url()` requires HTTPS and a filename matching
   `ruyi-<semver>.<arch>`.
3. The UI checks architecture compatibility.
4. `VersionDownloadDialog` requires explicit confirmation even when there is
   only one URL.
5. `VersionDownloadWorker` downloads to a temporary `.download` path.
6. The download implementation streams progress, supports cancellation, flushes
   and fsyncs the completed file, sets executable permissions, and uses atomic
   `os.replace()`.
7. Failure retains dialog output for retry; cancellation removes partial data.

The package download path is separate from standalone ruyi release download:

```text
ProvisionController
  -> download_child QProcess
       -> ruyi_adapter.ensure_repo()
       -> ruyi_adapter.run_download()
```

The child process owns package install output and process-group cancellation.
The controller routes its byte output through `RichTextView.feed_bytes()` and
does not flatten Rich/ANSI output.

## Activation and Deactivation

`version_manager.activate_version()` is the only low-level activation writer.
It verifies that the target is a regular file inside the managed versions
directory and rejects symlink targets. It creates a temporary symlink and uses
`os.replace()` for the managed link. If replacing an unmanaged existing file or
symlink, the user must confirm first; backup names are allocated as:

```text
ruyi.bak
ruyi.bak.1
ruyi.bak.2
...
```

Existing backups are never overwritten. A failed replacement attempts to
restore the moved unmanaged object.

If the activation parent is not user-writable, `VersionActivationWorker`
requests a password through a blocking Qt signal and invokes:

```text
sudo -S -p "" <executable> -m oh_my_ruyi.processes.version_activation_child activate ...
```

The password is written to stdin, never interpolated into a shell command. The
privileged child emits one JSON object; the worker reads activation state again
after the child exits.

Activation cancellation requests termination of the helper process group. A
local activation is a short atomic filesystem operation and cannot be rolled
back if cancellation arrives after it has committed; the worker reports the
completed result in that case rather than falsely claiming the link was
restored. First-use cancellation additionally prevents late activation results
from starting telemetry or repository continuation.

Deactivation removes only a managed activation link. Existing backups and
downloaded binaries remain. Deleting an active managed binary is rejected by
the infrastructure layer, not just disabled in the UI.

## Repository Configuration and Updates

Repository configuration has two distinct paths:

### Local configuration mutation

`infra/repo_manager.py` parses TOML for ordered display and validation. All
mutations use ruyi's `ConfigEditor`:

- add preset;
- edit default source;
- edit additional repository;
- enable/disable;
- remove additional repository.

The built-in `ruyisdk` entry remains first and cannot be removed. Additional
preset IDs and names are stable external identifiers. Local source paths must
be absolute.

### Remote update/news

`RepoManagementTab` owns update/news QProcesses. `repo_update_child` validates
that the config path ends in `ruyi/config.toml`, sets `XDG_CONFIG_HOME`, checks
the requested repository is active, and runs only that repository's native
update command. `repo_news_child` follows the same config isolation and allows
only `read` or `mark`.

Repository configuration mutations occur before the remote update starts. A
failed update does not roll back a committed source/branch/active change; the
UI reports that configuration and cached metadata may be out of sync.

`RepoController` owns blocking metadata init/sync used by provisioning. It does
not own the repository tab's update/news children. Its signals are connected
once when the main window is constructed; do not connect the same signal each
time a user retries sync.

## Provisioning State Safety

The provisioning state dependencies are:

```text
repo -> device -> variant -> combo -> package atoms
                                      -> prepared plan
                                      -> storage paths/fingerprints
                                      -> review/flash result
```

When navigating backward, `ProvisionStateMachine.invalidate_downstream()`
clears state below the destination. Changing a repository resets all selections
and prepared data. Starting a new package download also clears the prior plan,
storage mappings, fingerprints, and flash result.

Do not add a second mutable copy of these values to a page or controller. If a
new dependent value is introduced, add it to the appropriate `WizardState`
reset method and test backward navigation, retry, and repository replacement.

## Storage Discovery and Topology

All platform discovery uses `StorageDiscoveryWorker`; a quick Linux sysfs read
is still not allowed on the Qt thread.

### Linux

Discovery lists whole disks from `/sys/block`, skips loop/ram/zram/device-mapper
and md names, and records size/model, mounted state, and fingerprint. Mount
checks use:

- `/proc`/ruyi mount parsing;
- whole-disk and child partition relationships;
- sysfs `holders` relationships;
- Btrfs device groups.

This covers device-mapper, LUKS/LVM, RAID, and related stacked devices. If a
sysfs node, `dev` field, holder directory, or mount source cannot be resolved,
the topology is unknown and the operation fails closed.

### macOS

Discovery uses `diskutil list -plist` and `diskutil info -plist`, excludes
virtual disks, and selects `/dev/rdiskN` whole-disk paths. APFS containers,
physical stores, child identifiers, and mount points are followed. Missing
diskutil/APFS information is treated conservatively as mounted or unknown.

### Fingerprints

Linux fingerprints combine device numbers, sysfs nodes, WWID/UUID, serial,
disk sequence, size, and partition offsets. macOS fingerprints use stable
Media/Disk/Volume UUID data and may fall back to an IORegistry ID. Regular image
files use device/inode/size/mtime metadata; this detects target replacement but
is not a cryptographic content hash.

The Storage page records path and fingerprint at commit. A user-visible mounted
checkbox records explicit intent only; it does not replace revalidation.

## Review and Flash Boundaries

Before Review, the UI checks required commands, computes strategy pretend output,
and optionally runs `fastboot devices`. Before Flash:

1. The UI verifies that each requested path exists.
2. It verifies the recorded fingerprint when the platform check is safe to run
   synchronously; slow macOS topology checks are deferred to the worker.
3. It checks mount confirmation rules.
4. `FlashWorker.run()` validates every partition declared by
   `PreparedProvision.requested_host_blkdevs` before invoking any strategy.
5. Each plugin subprocess is intercepted by `call_subprocess_argv()`.
6. Every `dd` command must have exactly one explicit `of=` target matching the
   reviewed path.
7. Immediately before each actual `dd`, fingerprint and mounted state are
   checked again.

If a requested target is absent from the reviewed map, if a fingerprint is
missing or changed, if topology cannot be confirmed, or if an unconfirmed
mount appears, the worker fails before spawning the destructive command.

The current validator recognizes direct `dd` and the simple `sudo dd` shape.
Trusted strategy/plugin code must not hide destructive writes behind `sh -c`,
`env`, or another wrapper; Review output must be inspected when metadata or
plugins change.

Flash cancellation sends SIGTERM to the active command process group, drains
output while waiting briefly, and escalates to SIGKILL. Cancellation reports an
interrupted/recoverable state; it never promises rollback of bytes already
written. A nonzero strategy result stops later strategies and exposes Retry,
Review settings, and Start over.

## Output and Locale Safety

`QtRuyiLogger` and `RichTextView` preserve structured output. Use operation
targets (`welcome`, `device`, `download`, `flash`, `fastboot`, `pm`) so late
signals cannot leak into another operation's view.

Use:

- `feed_bytes()` for QProcess/subprocess chunks;
- `feed_text()` for decoded terminal text;
- `append_rich()` for Rich renderables;
- `append_plain_status()` only for non-terminal status messages.

QProcess setup goes through `configure_qprocess_environment()`. Raw subprocess
environments copy `os.environ` and merge `locale_environment()`. Locale is
selected once at startup using gettext precedence and encoding normalization;
Chinese activates only when both application and ruyi catalogs exist.

## Failure and Cancellation Matrix

| Operation | Cancellation owner | Failure UI | Cleanup guarantee |
| --- | --- | --- | --- |
| Release download | `VersionDownloadWorker` + response close | Dialog retains output and offers retry | Temporary download removed |
| Package download | `ProvisionController` + child process group | Download page recovery actions | Child process kill timer and output flush |
| Metadata init/sync | Controller/worker lifecycle | Welcome/Device status | Worker result/failure quits thread |
| Repository update | `RepoManagementTab` process group | Update dialog retains output | SIGTERM, then SIGKILL timer |
| News action | News child process | Update dialog message | Process identity and finished handler |
| Activation | `VersionActivationWorker` / sudo child | Version status or first-use stage | Process group termination and worker cleanup |
| Disk discovery | `StorageDiscoveryWorker` | Storage error and file chooser | Worker thread cleanup |
| Flash | `FlashWorker` + subprocess group | Flash recovery actions | Prompt restoration, output flush, thread cleanup |
| Telemetry | `TelemetrySetupWorker` + PTY helper | Version status | PTY/file descriptor/process cleanup |

Every new cancellation path must test the cancellation request, the late
result/failure, the visible state after cancellation, and resource cleanup.

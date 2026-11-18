# Pinned upstream patches

These patches extend the **pinned** OrangeFox sources without forking them.
They are applied by `build/apply_patches.sh` during `build/sync.sh`,
`build/run-all.sh` and `build/build.sh`, so a local build and a CI build run the
same code.

| Patch | Target repo | Upstream revision | Purpose |
|---|---|---|---|
| `0001-theme-sakura-diagnostics.patch` | `bootable/recovery` | `8d2aad19deb158e935d70ca5b648162c2b2831ee` | Adds Settings → Error Logs, the diagnostic text viewer pages and the status-bar `! DIAG` badge |

## Why a theme patch and not a C++ fork

The pinned GUI already provides everything the feature needs:

* `cmd` runs a shell command in a worker thread (`gui/action.cpp`);
* `set` stores a GUI variable;
* `page` switches pages;
* `cat_file` (`pages/files.xml`) renders a file into a scrollable textbox
  through `of_file_to_read` (`gui/listbox.cpp`), rejecting files > 1.5 MiB;
* `DataManager::GetValue()` resolves `property.<name>`, so a condition can read
  `property.of.boot_diag_errors` that the boot logger sets with `setprop`.

Therefore **no C++ change is required**. The patch only touches theme XML and
English strings. If a future upstream change removes one of those actions, the
patch fails to apply and the build stops — it never silently degrades.

## Rules

1. Never edit the files by hand after applying; regenerate the patch instead.
2. `patches/PINNED_REVISIONS` must match `build/sync.sh`. The static checks
   compare them.
3. `git apply --check` must pass before anything is written. A changed context
   is a hard failure (this is tested by `tests/test_patches.py`).
4. Re-running is idempotent: a patch already applied (reverse check succeeds)
   is skipped.
5. To regenerate after an upstream bump:

```bash
git clone -b fox_12.1 https://gitlab.com/OrangeFox/bootable/Recovery.git /tmp/ofx
git -C /tmp/ofx checkout <new-sha>
# edit gui/theme/... exactly as the current patch does
git -C /tmp/ofx add -N gui/theme/portrait_hdpi/pages/diag.xml
git -C /tmp/ofx diff > patches/0001-theme-sakura-diagnostics.patch
# update patches/PINNED_REVISIONS and RECOVERY_SHA in build/sync.sh together
```

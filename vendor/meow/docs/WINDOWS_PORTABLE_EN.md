# meow4.5.3 · Windows portable

For Windows10/11 Intel/AMD x64. Python and dependencies are bundled and isolated; no Python installation or PATH setup is required.

1. Extract the complete windows-x64-portable-en.zip into a new writable directory.
2. Run start.bat; do not run inside the ZIP or remove the python directory.
3. If needed, open http://127.0.0.1:8765/. Use `start.bat --port 8794` for another port.

The scorer, baselines and update flow match source distributions. One-click updates prepare a new directory, wait for tasks, restart and roll back a failed startup. Entering4.5.3 from4.5.2 needs the new launcher once; stop the old backend, then optionally use --migrate-from. Original data is preserved; vault references do not copy keys between computers.

Closing the browser does not stop the backend. Finish detections, pause schedules and use Settings → Stop local service. The original start.bat opens the currently installed version. Reports in meow_runs are not recalculated by updates.

PORTABLE_BUILD.json records Python/dependencies/hashes. Checksums are in SHA256SUMS.txt. Python's license is python/LICENSE.txt; dependency licenses remain in.dist-info directories. See README_SOURCE_EN.md for source installation and TECHNICAL_REPORT_EN.md for statistical limitations.

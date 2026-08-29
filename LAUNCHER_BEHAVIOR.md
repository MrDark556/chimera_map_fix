# Launcher Discovery Behavior — v3.6.1

1. If `haloce.exe` is beside `haloce_chimera_mpdlr.exe`, it is used automatically.
2. Otherwise, a previously confirmed saved Halo path is used.
3. Otherwise, common Halo CE install locations are searched. If found, the user is asked to confirm the exact path.
4. If the user says No, or no install is found, a file picker asks for the original `haloce.exe`.
5. The confirmed/manual location is remembered.

`haloce_chimera_mpdlr.exe` is NOT a replacement for the original `haloce.exe`.

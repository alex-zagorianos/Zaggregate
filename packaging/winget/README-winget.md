# Publishing Zaggregate to winget (template — not yet submitted)

This folder holds a **template** winget manifest set for Zaggregate. Nothing here
is a live submission — every `{{PLACEHOLDER}}` must be filled in before a real
release, and no PR to `microsoft/winget-pkgs` has been opened.

## Why winget

A `winget install Zaggregate.Zaggregate` skips the SmartScreen "unknown
publisher" dialog a plain unsigned-exe download triggers: the winget validation
pipeline vets the package, and the CLI install path doesn't show the soft block.
It's a free way to make the beta easy and trustworthy to install, with no code-
signing certificate required.

## The files

winget uses a **three-file multi-manifest** per version, all sharing the same
`PackageIdentifier` (`Zaggregate.Zaggregate`) and `PackageVersion`:

| File                                      | Role                                          |
| ----------------------------------------- | --------------------------------------------- |
| `Zaggregate.Zaggregate.yaml`              | version manifest (ties the set together)      |
| `Zaggregate.Zaggregate.installer.yaml`    | how to fetch + install (the zip URL + SHA256) |
| `Zaggregate.Zaggregate.locale.en-US.yaml` | name, publisher, description, tags            |

Zaggregate ships as a **portable zip** (no MSI/installer), so the installer
manifest uses `InstallerType: zip` + `NestedInstallerType: portable` and registers
`JobProgram.exe` under the command alias `zaggregate`.

## Filling in the placeholders

For a real release, replace every `{{PLACEHOLDER}}`:

- `{{VERSION}}` — the release version. **Must match `config.APP_VERSION`** and the
  three files must agree. (Currently `1.0.0`.)
- `{{INSTALLER_URL}}` — the public GitHub release asset URL for the built
  `Zaggregate-vX.Y.Z.zip`.
- `{{SHA256}}` — the archive's SHA-256, uppercase hex, no spaces. Take it from the
  `SHA256SUMS.txt` that `build_package.py` emits next to the zip
  (`certutil -hashfile Zaggregate-vX.Y.Z.zip SHA256` also prints it).
- `{{PUBLISHER}}`, `{{PUBLISHER_URL}}`, `{{SUPPORT_URL}}`, `{{PACKAGE_URL}}`,
  `{{LICENSE_URL}}` — the owner name and the relevant GitHub URLs. (`Owner`/`Repo`
  default to the same repo `config.UPDATE_REPO` points at.)

Note: `License: Proprietary` is intentional — the open-source license is a pending
decision (see `EULA.txt`; all rights reserved for now). Update it once a license
is chosen.

## Validating and submitting (when the time comes)

1. Build the release and get its checksum:
   ```
   py -3.12 build_package.py            # -> dist/Zaggregate-vX.Y.Z.zip + SHA256SUMS.txt
   ```
2. Upload the zip as a GitHub release asset; copy its URL into `{{INSTALLER_URL}}`.
3. Validate locally with the winget CLI:
   ```
   winget validate --manifest packaging\winget
   winget install --manifest packaging\winget   # optional local install test
   ```
4. Submit: fork `microsoft/winget-pkgs`, place the three files under
   `manifests/z/Zaggregate/Zaggregate/<version>/`, and open a PR. The
   `wingetcreate` tool can automate steps 3–4:
   ```
   wingetcreate update Zaggregate.Zaggregate --version X.Y.Z --urls <installer-url>
   ```

The manifest schema version here is `1.6.0`; bump it if winget requires a newer
one at submission time.

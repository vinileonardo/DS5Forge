# DS5Forge Release Signing Setup

DS5Forge uses the Tauri updater signing keypair to authenticate updater artifacts. This is separate from Windows Authenticode/code signing.

## Security rules

- Generate the keypair once and keep the private key outside the repository.
- Never paste the private key into source files, issues, PRs, logs, chat or support bundles.
- Back up the private key and its password in a secure password manager/vault. Losing it prevents publishing trusted updates to existing installations.
- The public key is not secret, but this project injects it through the release workflow so the checked-in base Tauri config remains non-release-safe by itself.
- The release workflow receives credentials only through GitHub Actions Secrets.

## Generate the updater keypair

Run from WSL/Linux so `~` resolves to your home directory:

```bash
cd ~/projetos/DS5Forge/frontend
mkdir -p ~/.tauri
npm ci
npm run tauri signer generate -- -w ~/.tauri/ds5forge.key
```

The command prompts for a password. Use a strong password and store it with the private key. It creates:

```text
~/.tauri/ds5forge.key      # PRIVATE — never commit/share
~/.tauri/ds5forge.key.pub  # public verification key
```

The repository currently resolves `@tauri-apps/cli` 2.11.4. Do not generate production updater keys with a CLI older than 2.10.1 because Tauri fixed a key-generation regression in 2.10.1.

## Configure GitHub Actions Secrets without printing the key

From WSL:

```bash
gh secret set TAURI_SIGNING_PRIVATE_KEY \
  --repo vinileonardo/DS5Forge \
  < ~/.tauri/ds5forge.key

gh secret set TAURI_SIGNING_PUBLIC_KEY \
  --repo vinileonardo/DS5Forge \
  < ~/.tauri/ds5forge.key.pub

read -rsp "Tauri signing key password: " TAURI_KEY_PASSWORD
echo
printf '%s' "$TAURI_KEY_PASSWORD" | gh secret set TAURI_SIGNING_PRIVATE_KEY_PASSWORD \
  --repo vinileonardo/DS5Forge
unset TAURI_KEY_PASSWORD
```

Verify only the secret names, never their values:

```bash
gh secret list --repo vinileonardo/DS5Forge
```

Expected names:

```text
TAURI_SIGNING_PRIVATE_KEY
TAURI_SIGNING_PRIVATE_KEY_PASSWORD
TAURI_SIGNING_PUBLIC_KEY
```

## Release behavior

A signed tag such as `v0.4.0-rc.1` triggers `.github/workflows/windows-release.yml`.

The workflow:

1. validates that the tag exactly matches `VERSION` and all version consumers;
2. builds the packaged Python sidecar;
3. builds the per-user NSIS application with Tauri updater signing enabled;
4. generates `latest.json` and `SHA256SUMS.txt`;
5. preserves the complete artifact set as a GitHub Actions artifact;
6. publishes a versioned GitHub prerelease/release;
7. refreshes the fixed `update-rc/latest.json` channel used by prerelease installations.

RC builds embed the `update-rc` endpoint. Stable builds embed GitHub's `releases/latest` endpoint. Publishing stable also refreshes `update-rc` so an installed RC can upgrade to the final version.

## Windows publisher warnings

Tauri updater signing proves that an update was produced by the holder of the updater private key. It does not make the NSIS executable an Authenticode-signed Windows application. Until Windows code signing is added, internal RC installers may still show SmartScreen/Unknown Publisher warnings. That is expected for this phase and must not be confused with an updater-signature failure.
